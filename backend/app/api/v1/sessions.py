"""Session flow endpoints: create, consent, recording-url, finish, analysis, report."""
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import Principal, require_roles
from app.core.storage import get_storage
from app.db import get_db
from app.schemas.sessions import (
    ConsentIn,
    FinishIn,
    RecordingUrlIn,
    SessionCreateIn,
)
from app.services import session_service

router = APIRouter(tags=["sessions"])


def _base_url(request: Request) -> str:
    return str(request.base_url)


@router.post("/sessions", status_code=201)
async def create_session(
    body: SessionCreateIn,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await session_service.create_session(db, principal, body, idempotency_key)


@router.post("/sessions/{session_id}/consent")
async def consent(
    session_id: str,
    body: ConsentIn,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await session_service.register_consent(db, principal, session_id, body)


@router.post("/sessions/{session_id}/recording-url")
async def recording_url(
    session_id: str,
    body: RecordingUrlIn,
    request: Request,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await session_service.issue_recording_url(
        db,
        principal,
        session_id,
        body.contentType,
        body.durationSeconds,
        _base_url(request),
        get_storage(),
    )


@router.post("/sessions/{session_id}/finish", status_code=202)
async def finish(
    session_id: str,
    body: FinishIn,
    request: Request,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await session_service.finish_session(
        db, principal, session_id, body.blobPath, get_storage(), get_settings()
    )
    worker = getattr(request.app.state, "analysis_worker", None)
    if worker is not None:
        import uuid as _uuid

        worker.enqueue(_uuid.UUID(result["analysisId"]))
    return result


@router.get("/sessions/{session_id}/analysis")
async def analysis_status(
    session_id: str,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await session_service.get_analysis_status(db, principal, session_id)


@router.get("/sessions/{session_id}/report")
async def report(
    session_id: str,
    request: Request,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await session_service.get_report(
        db, principal, session_id, _base_url(request), get_storage()
    )
