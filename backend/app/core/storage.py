"""Recording storage abstraction with a local-disk, SAS-style implementation.

The interface mimics single-use, expiring SAS URLs so a Blob Storage / S3
backend can be plugged in later without touching the API layer.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.utils import utcnow


@dataclass
class UploadGrant:
    upload_url: str
    blob_path: str
    expires_at: datetime
    max_size_bytes: int


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload: dict, secret: str) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _verify(token: str, secret: str) -> dict:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        raise AppError(401, "unauthorized", "URL firmada inválida.")
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise AppError(401, "unauthorized", "URL firmada inválida.")
    try:
        padding = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + padding))
    except (ValueError, json.JSONDecodeError):
        raise AppError(401, "unauthorized", "URL firmada inválida.")
    if int(payload.get("exp", 0)) < int(utcnow().timestamp()):
        raise AppError(401, "unauthorized", "La URL firmada ha caducado.")
    return payload


class StorageService(ABC):
    """Pluggable recording storage (SAS-like upload/download URLs)."""

    @abstractmethod
    def create_upload_grant(
        self,
        base_url: str,
        session_id: uuid.UUID,
        content_type: str,
        duration_seconds: int | None,
    ) -> UploadGrant: ...

    @abstractmethod
    def create_read_url(self, base_url: str, blob_path: str) -> str: ...

    @abstractmethod
    def verify_upload_token(self, token: str) -> dict: ...

    @abstractmethod
    def verify_read_token(self, token: str) -> dict: ...

    @abstractmethod
    def exists(self, blob_path: str) -> bool: ...

    @abstractmethod
    def size(self, blob_path: str) -> int | None: ...

    @abstractmethod
    def write(self, blob_path: str, data: bytes) -> None: ...

    @abstractmethod
    def full_path(self, blob_path: str) -> Path: ...

    @abstractmethod
    def delete(self, blob_path: str) -> None: ...

    @abstractmethod
    def pop_pending(self, blob_path: str) -> dict: ...


class LocalDiskStorage(StorageService):
    """Stores blobs under ./storage and signs one-use upload / read URLs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = Path(settings.storage_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        # In-memory metadata for pending uploads (dev backend limitation).
        self._pending: dict[str, dict] = {}
        self._used_jti: set[str] = set()

    # -- URL issuing ------------------------------------------------------
    def create_upload_grant(
        self,
        base_url: str,
        session_id: uuid.UUID,
        content_type: str,
        duration_seconds: int | None,
    ) -> UploadGrant:
        now = utcnow()
        ext = "webm" if "webm" in content_type else "mp4"
        blob_path = f"rec/{now:%Y}/{now:%m}/sess-{session_id}.{ext}"
        expires_at = now + timedelta(minutes=self._settings.upload_url_ttl_minutes)
        jti = uuid.uuid4().hex
        token = _sign(
            {
                "purpose": "upload",
                "blob": blob_path,
                "jti": jti,
                "exp": int(expires_at.timestamp()),
            },
            self._settings.upload_signing_secret,
        )
        self._pending[blob_path] = {
            "content_type": content_type,
            "duration_seconds": duration_seconds,
            "jti": jti,
        }
        return UploadGrant(
            upload_url=f"{base_url.rstrip('/')}/v1/uploads/{token}",
            blob_path=blob_path,
            expires_at=expires_at,
            max_size_bytes=self._settings.max_upload_size_bytes,
        )

    def create_read_url(self, base_url: str, blob_path: str) -> str:
        expires_at = utcnow() + timedelta(
            minutes=self._settings.read_url_ttl_minutes
        )
        token = _sign(
            {
                "purpose": "read",
                "blob": blob_path,
                "jti": uuid.uuid4().hex,
                "exp": int(expires_at.timestamp()),
            },
            self._settings.upload_signing_secret,
        )
        return f"{base_url.rstrip('/')}/v1/uploads/{token}"

    # -- URL verification ---------------------------------------------------
    def verify_upload_token(self, token: str) -> dict:
        payload = _verify(token, self._settings.upload_signing_secret)
        if payload.get("purpose") != "upload":
            raise AppError(401, "unauthorized", "URL firmada inválida.")
        jti = payload.get("jti")
        if jti in self._used_jti:
            raise AppError(401, "unauthorized", "La URL de carga ya fue utilizada.")
        pending = self._pending.get(payload.get("blob", ""))
        if pending is None or pending.get("jti") != jti:
            raise AppError(401, "unauthorized", "La URL de carga no es válida.")
        return payload

    def mark_used(self, jti: str) -> None:
        self._used_jti.add(jti)

    def verify_read_token(self, token: str) -> dict:
        payload = _verify(token, self._settings.upload_signing_secret)
        if payload.get("purpose") != "read":
            raise AppError(401, "unauthorized", "URL firmada inválida.")
        return payload

    # -- Blob operations ----------------------------------------------------
    def full_path(self, blob_path: str) -> Path:
        path = (self._root / blob_path).resolve()
        if self._root.resolve() not in path.parents:
            raise AppError(400, "invalid_request", "Ruta de blob inválida.")
        return path

    def exists(self, blob_path: str) -> bool:
        try:
            return self.full_path(blob_path).is_file()
        except AppError:
            return False

    def size(self, blob_path: str) -> int | None:
        try:
            return self.full_path(blob_path).stat().st_size
        except OSError:
            return None

    def write(self, blob_path: str, data: bytes) -> None:
        path = self.full_path(blob_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, blob_path: str) -> None:
        try:
            self.full_path(blob_path).unlink(missing_ok=True)
        except OSError:
            pass

    def pop_pending(self, blob_path: str) -> dict:
        return self._pending.pop(blob_path, {})


_storage: StorageService | None = None


def init_storage(settings: Settings | None = None) -> StorageService:
    global _storage
    _storage = LocalDiskStorage(settings or get_settings())
    return _storage


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = LocalDiskStorage(get_settings())
    return _storage
