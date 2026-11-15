"""Seal the exact recording bytes analyzed by the worker.

The sealed blob name is content-addressed and job-scoped. Uploads never use
overwrite, so a mutable source blob can change later without changing the
evidence referenced by a labeling case.
"""

import hashlib
import mimetypes
import re
import time
from pathlib import Path


DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 0.25
SUPPORTED_EXTENSIONS = frozenset((".webm", ".mp4"))


class RecordingEvidenceError(RuntimeError):
    """The analyzed media could not be sealed or verified."""


def _safe_segment(value, label):
    normalized = str(value or "").strip().lower()
    if not normalized or not re.fullmatch(r"[a-z0-9-]{1,80}", normalized):
        raise RecordingEvidenceError(f"{label} no es un identificador seguro.")
    return normalized


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _properties_value(properties, name, default=None):
    if isinstance(properties, dict):
        return properties.get(name, default)
    return getattr(properties, name, default)


def _is_retryable_storage_error(error):
    if type(error).__name__ in {
        "ServiceRequestError",
        "ServiceResponseError",
        "ServiceResponseTimeoutError",
    }:
        return True
    status_code = getattr(error, "status_code", None)
    return status_code in {408, 429} or (
        isinstance(status_code, int) and 500 <= status_code < 600
    )


def _read_verified_properties(
    blob_client,
    *,
    digest,
    expected_size=None,
    expected_session_id=None,
    expected_job_id=None,
):
    properties = blob_client.get_blob_properties()
    metadata = _properties_value(properties, "metadata", {}) or {}
    actual_size = _properties_value(properties, "size")
    if str(metadata.get("sealed", "")).lower() != "true":
        raise RecordingEvidenceError("El blob no declara evidencia sellada.")
    if str(metadata.get("sha256", "")).lower() != digest:
        raise RecordingEvidenceError(
            "El blob sellado existente no coincide con el SHA-256 analizado."
        )
    if expected_session_id and str(metadata.get("sessionid", "")).lower() != str(
        expected_session_id
    ).lower():
        raise RecordingEvidenceError("La evidencia no corresponde a la sesión esperada.")
    if expected_job_id and str(metadata.get("jobid", "")).lower() != str(
        expected_job_id
    ).lower():
        raise RecordingEvidenceError("La evidencia no corresponde al job esperado.")
    if (
        expected_size is not None
        and actual_size is not None
        and int(actual_size) != int(expected_size)
    ):
        raise RecordingEvidenceError(
            "El blob sellado existente no coincide con el tamaño analizado."
        )

    etag = str(_properties_value(properties, "etag", "") or "").strip()
    if not etag:
        raise RecordingEvidenceError("La evidencia sellada no devolvió ETag.")
    content_type = _properties_value(properties, "content_type")
    if not content_type:
        settings = _properties_value(properties, "content_settings")
        content_type = _properties_value(settings, "content_type")
    content_type = str(content_type or "").strip().lower()
    if not content_type.startswith("video/"):
        raise RecordingEvidenceError(
            "La evidencia sellada no devolvió un tipo de contenido de video."
        )
    return properties, etag, content_type, actual_size


def verify_recording_evidence(
    *,
    blob_service,
    container_name,
    evidence,
    expected_session_id=None,
    expected_job_id=None,
):
    """Verify an explicit sealed-evidence manifest against Blob properties."""
    if not isinstance(evidence, dict):
        raise RecordingEvidenceError("La evidencia debe ser un objeto.")
    sealed_path = str(evidence.get("sealedPath") or "").strip()
    digest = str(evidence.get("sha256") or "").strip().lower()
    expected_etag = str(evidence.get("etag") or "").strip().strip('"')
    expected_type = str(evidence.get("contentType") or "").strip().lower()
    if not sealed_path.startswith("labeling-evidence/") or ".." in sealed_path:
        raise RecordingEvidenceError("sealedPath no es válido.")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RecordingEvidenceError("sha256 no es válido.")
    if not expected_etag or not expected_type.startswith("video/"):
        raise RecordingEvidenceError("La evidencia carece de ETag o tipo de video.")

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=sealed_path,
        version_id=evidence.get("versionId") or None,
    )
    properties, actual_etag, actual_type, actual_size = _read_verified_properties(
        blob_client,
        digest=digest,
        expected_size=evidence.get("sizeBytes"),
        expected_session_id=expected_session_id,
        expected_job_id=expected_job_id,
    )
    if actual_etag.strip('"') != expected_etag or actual_type != expected_type:
        raise RecordingEvidenceError(
            "La identidad del blob no coincide con el manifiesto sellado."
        )
    version_id = _properties_value(properties, "version_id")
    expected_version = evidence.get("versionId") or None
    if expected_version and str(version_id or "") != str(expected_version):
        raise RecordingEvidenceError(
            "La versión del blob no coincide con el manifiesto sellado."
        )
    return {
        "sealedPath": sealed_path,
        "versionId": str(version_id) if version_id else None,
        "sha256": digest,
        "etag": actual_etag,
        "contentType": actual_type,
        "sizeBytes": int(actual_size) if actual_size is not None else None,
        "durationSeconds": evidence.get("durationSeconds"),
    }


def _upload_and_verify(
    *,
    blob_client,
    local,
    digest,
    metadata,
    content_settings,
):
    try:
        with local.open("rb") as stream:
            kwargs = {"overwrite": False, "metadata": metadata}
            if content_settings is not None:
                kwargs["content_settings"] = content_settings
            blob_client.upload_blob(stream, **kwargs)
    except Exception as error:
        if type(error).__name__ not in {"ResourceExistsError", "BlobAlreadyExists"}:
            raise

    properties, etag, content_type, _ = _read_verified_properties(
        blob_client,
        digest=digest,
        expected_size=local.stat().st_size,
        expected_session_id=metadata["sessionid"],
        expected_job_id=metadata["jobid"],
    )
    return properties, etag, content_type


def seal_recording_evidence(
    *,
    storage_connection_string,
    container_name,
    source_blob_path,
    local_path,
    session_id,
    job_id,
    blob_service=None,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    retry_delay_seconds=DEFAULT_RETRY_DELAY_SECONDS,
    sleep_fn=time.sleep,
):
    """Upload and verify immutable evidence, retrying only transient SDK failures."""
    if not storage_connection_string and blob_service is None:
        raise RecordingEvidenceError("Storage es obligatorio para sellar la grabación.")
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise RecordingEvidenceError("max_attempts debe ser un entero positivo.")
    local = Path(local_path)
    if not local.is_file() or local.stat().st_size <= 0:
        raise RecordingEvidenceError("La grabación local está vacía o no existe.")

    safe_session = _safe_segment(session_id, "sessionId")
    safe_job = _safe_segment(job_id, "jobId")
    digest = sha256_file(local)
    extension = Path(str(source_blob_path or "")).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise RecordingEvidenceError("La grabación debe ser WebM o MP4.")
    content_type = mimetypes.types_map.get(extension)
    if not content_type or not content_type.startswith("video/"):
        raise RecordingEvidenceError("No se pudo determinar el tipo de video.")
    sealed_path = f"labeling-evidence/{safe_session}/{safe_job}/{digest}{extension}"

    content_settings = None
    if blob_service is None:
        from azure.storage.blob import BlobServiceClient, ContentSettings

        blob_service = BlobServiceClient.from_connection_string(
            storage_connection_string
        )
        content_settings = ContentSettings(content_type=content_type)

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=sealed_path,
    )
    metadata = {
        "sha256": digest,
        "sessionid": safe_session,
        "jobid": safe_job,
        "sealed": "true",
    }

    for attempt in range(1, max_attempts + 1):
        try:
            properties, etag, actual_content_type = _upload_and_verify(
                blob_client=blob_client,
                local=local,
                digest=digest,
                metadata=metadata,
                content_settings=content_settings,
            )
            break
        except RecordingEvidenceError:
            raise
        except Exception as error:
            if attempt == max_attempts or not _is_retryable_storage_error(error):
                raise RecordingEvidenceError(
                    f"No se pudo sellar la grabación ({type(error).__name__})."
                ) from error
            sleep_fn(retry_delay_seconds * (2 ** (attempt - 1)))

    version_id = _properties_value(properties, "version_id")

    return {
        "sealedPath": sealed_path,
        "versionId": str(version_id) if version_id else None,
        "sha256": digest,
        "etag": etag,
        "contentType": actual_content_type,
        "sizeBytes": int(local.stat().st_size),
        "sourceBlobPath": str(source_blob_path),
        "durationSeconds": None,
    }
