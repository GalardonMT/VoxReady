"""Signed upload/download endpoints (SAS-style, token-authenticated)."""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.config import get_settings
from app.core.errors import AppError
from app.core.storage import get_storage

router = APIRouter(tags=["uploads"])


@router.put("/uploads/{token}")
async def upload_blob(token: str, request: Request) -> dict:
    """Receive the recording binary through a signed, single-use URL."""
    storage = get_storage()
    payload = storage.verify_upload_token(token)
    data = await request.body()
    if len(data) > get_settings().max_upload_size_bytes:
        raise AppError(
            400, "invalid_request", "El archivo excede el tamaño máximo permitido."
        )
    storage.write(payload["blob"], data)
    storage.mark_used(payload["jti"])
    return {"blobPath": payload["blob"], "sizeBytes": len(data)}


@router.get("/uploads/{token}")
async def download_blob(token: str) -> FileResponse:
    """Serve a recording through a signed, expiring read URL."""
    storage = get_storage()
    payload = storage.verify_read_token(token)
    blob_path = payload["blob"]
    if not storage.exists(blob_path):
        raise AppError(404, "not_found", "La grabación no existe o fue purgada.")
    media_type = "video/webm" if blob_path.endswith(".webm") else "video/mp4"
    return FileResponse(storage.full_path(blob_path), media_type=media_type)
