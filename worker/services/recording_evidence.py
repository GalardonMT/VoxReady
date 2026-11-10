"""Seal the exact recording bytes analyzed by the worker.

The sealed blob name is content-addressed and job-scoped. Uploads never use
overwrite, so a mutable source blob can change later without changing the
evidence referenced by a labeling case.
"""

import hashlib
import mimetypes
import re
from pathlib import Path


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


def seal_recording_evidence(
    *,
    storage_connection_string,
    container_name,
    source_blob_path,
    local_path,
    session_id,
    job_id,
    blob_service=None,
):
    """Upload the local analyzed bytes once and return immutable identity data."""
    if not storage_connection_string and blob_service is None:
        raise RecordingEvidenceError("Storage es obligatorio para sellar la grabación.")
    local = Path(local_path)
    if not local.is_file() or local.stat().st_size <= 0:
        raise RecordingEvidenceError("La grabación local está vacía o no existe.")

    safe_session = _safe_segment(session_id, "sessionId")
    safe_job = _safe_segment(job_id, "jobId")
    digest = sha256_file(local)
    extension = Path(str(source_blob_path or "")).suffix.lower()
    if extension not in (".webm", ".mp4"):
        extension = ".bin"
    content_type = mimetypes.types_map.get(extension, "application/octet-stream")
    sealed_path = f"labeling-evidence/{safe_session}/{safe_job}/{digest}{extension}"

    content_settings = None
    resource_exists_names = {"ResourceExistsError", "BlobAlreadyExists"}
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
    try:
        with local.open("rb") as stream:
            kwargs = {
                "overwrite": False,
                "metadata": metadata,
            }
            if content_settings is not None:
                kwargs["content_settings"] = content_settings
            blob_client.upload_blob(stream, **kwargs)
    except Exception as error:
        if type(error).__name__ not in resource_exists_names:
            raise RecordingEvidenceError(
                f"No se pudo sellar la grabación ({type(error).__name__})."
            ) from error

    properties = blob_client.get_blob_properties()
    actual_metadata = _properties_value(properties, "metadata", {}) or {}
    actual_size = _properties_value(properties, "size")
    if str(actual_metadata.get("sha256", "")).lower() != digest:
        raise RecordingEvidenceError(
            "El blob sellado existente no coincide con el SHA-256 analizado."
        )
    if actual_size is not None and int(actual_size) != local.stat().st_size:
        raise RecordingEvidenceError(
            "El blob sellado existente no coincide con el tamaño analizado."
        )

    etag = str(_properties_value(properties, "etag", "") or "").strip()
    if not etag:
        raise RecordingEvidenceError("La evidencia sellada no devolvió ETag.")
    version_id = _properties_value(properties, "version_id")
    actual_content_type = _properties_value(properties, "content_type")
    if not actual_content_type:
        settings = _properties_value(properties, "content_settings")
        actual_content_type = _properties_value(settings, "content_type")

    return {
        "sealedPath": sealed_path,
        "versionId": str(version_id) if version_id else None,
        "sha256": digest,
        "etag": etag,
        "contentType": str(actual_content_type or content_type),
        "sizeBytes": int(local.stat().st_size),
        "sourceBlobPath": str(source_blob_path),
        "durationSeconds": None,
    }
