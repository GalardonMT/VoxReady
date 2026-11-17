from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.recording_evidence import (
    RecordingEvidenceError,
    seal_recording_evidence,
    verify_recording_evidence,
)


class ServiceRequestError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class FakeBlobClient:
    def __init__(self, *, failures=0, content_type="video/webm", version_id="v1"):
        self.failures = failures
        self.content_type = content_type
        self.version_id = version_id
        self.content = b""
        self.metadata = {}
        self.upload_attempts = 0

    def upload_blob(self, stream, *, overwrite, metadata, **_kwargs):
        assert overwrite is False
        self.upload_attempts += 1
        if self.upload_attempts <= self.failures:
            raise ServiceRequestError("temporary outage")
        self.content = stream.read()
        self.metadata = metadata

    def get_blob_properties(self):
        return {
            "metadata": self.metadata,
            "size": len(self.content),
            "etag": '"etag"',
            "version_id": self.version_id,
            "content_type": self.content_type,
        }


class FakeBlobService:
    def __init__(self, client):
        self.client = client

    def get_blob_client(self, *, container, blob, version_id=None):
        assert container == "recordings"
        assert blob.startswith("labeling-evidence/")
        if version_id is not None:
            assert version_id == "v1"
        return self.client


def seal(source, client, **overrides):
    return seal_recording_evidence(
        storage_connection_string=None,
        container_name="recordings",
        source_blob_path="recordings/session.webm",
        local_path=source,
        session_id="10000000-0000-4000-8000-000000000001",
        job_id="20000000-0000-4000-8000-000000000001",
        blob_service=FakeBlobService(client),
        sleep_fn=lambda _seconds: None,
        **overrides,
    )


def test_seal_retries_transient_upload_and_returns_verified_evidence(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient(failures=2)

    evidence = seal(source, client)

    assert client.upload_attempts == 3
    assert evidence["etag"] == '"etag"'
    assert evidence["contentType"] == "video/webm"


def test_seal_stops_after_bounded_attempts(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient(failures=3)

    with pytest.raises(RecordingEvidenceError, match="ServiceRequestError"):
        seal(source, client, max_attempts=2)

    assert client.upload_attempts == 2


def test_seal_rejects_unverified_content_type_without_retry(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient(content_type="application/octet-stream")

    with pytest.raises(RecordingEvidenceError, match="tipo de contenido de video"):
        seal(source, client)

    assert client.upload_attempts == 1


def test_seal_does_not_retry_non_transient_storage_failure(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient()

    def reject_upload(*_args, **_kwargs):
        client.upload_attempts += 1
        raise AuthenticationError("forbidden")

    client.upload_blob = reject_upload

    with pytest.raises(RecordingEvidenceError, match="AuthenticationError"):
        seal(source, client)

    assert client.upload_attempts == 1


def test_verify_manifest_binds_blob_to_expected_session_and_job(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient()
    service = FakeBlobService(client)
    evidence = seal(source, client)

    verified = verify_recording_evidence(
        blob_service=service,
        container_name="recordings",
        evidence=evidence,
        expected_session_id="10000000-0000-4000-8000-000000000001",
        expected_job_id="20000000-0000-4000-8000-000000000001",
    )

    assert verified["sealedPath"] == evidence["sealedPath"]
    assert verified["sha256"] == evidence["sha256"]


def test_verify_manifest_rejects_wrong_session_identity(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient()
    service = FakeBlobService(client)
    evidence = seal(source, client)

    with pytest.raises(RecordingEvidenceError, match="sesión esperada"):
        verify_recording_evidence(
            blob_service=service,
            container_name="recordings",
            evidence=evidence,
            expected_session_id="wrong-session",
        )


def test_verify_manifest_rejects_blob_without_sealed_metadata(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient()
    service = FakeBlobService(client)
    evidence = seal(source, client)
    client.metadata.pop("sealed")

    with pytest.raises(RecordingEvidenceError, match="evidencia sellada"):
        verify_recording_evidence(
            blob_service=service,
            container_name="recordings",
            evidence=evidence,
        )


def test_verify_manifest_rejects_changed_blob_version(tmp_path):
    source = tmp_path / "recording.webm"
    source.write_bytes(b"recording")
    client = FakeBlobClient()
    service = FakeBlobService(client)
    evidence = seal(source, client)
    client.version_id = "v2"

    with pytest.raises(RecordingEvidenceError, match="versión del blob"):
        verify_recording_evidence(
            blob_service=service,
            container_name="recordings",
            evidence=evidence,
        )
