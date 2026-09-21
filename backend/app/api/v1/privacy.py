"""Privacy endpoints: deletion requests (spokesperson + client admin)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, pagination_params, to_uuid
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.core.storage import get_storage
from app.db import get_db
from app.models.privacy import DeletionRequest
from app.models.recording import Recording
from app.models.sessions import PracticeSession
from app.schemas.privacy import DeletionRequestIn
from app.services.helpers import audit
from app.utils import iso, utcnow

router = APIRouter(tags=["privacy"])


@router.post("/me/deletion-requests", status_code=201)
async def create_deletion_request(
    body: DeletionRequestIn,
    principal: Principal = Depends(require_roles("spokesperson")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session_id = None
    if body.sessionId:
        session_id = to_uuid(body.sessionId, "session_not_found")
        session = await db.get(PracticeSession, session_id)
        if (
            session is None
            or session.is_deleted
            or session.user_id != principal.user_id
        ):
            raise AppError(
                404,
                "session_not_found",
                "La sesión indicada no existe o no pertenece al usuario.",
            )

    request = DeletionRequest(
        client_id=principal.client_id,
        subject_user_id=principal.user_id,
        session_id=session_id,
        reason=body.reason,
        status="pending",
        requested_at=utcnow(),
    )
    db.add(request)
    audit(
        db,
        "deletion_requested",
        actor_user_id=principal.user_id,
        client_id=principal.client_id,
        entity_type="deletion_request",
        entity_id=request.id,
        detail={"sessionId": str(session_id) if session_id else None},
    )
    await db.commit()
    return {
        "requestId": str(request.id),
        "status": "pending",
        "requestedAt": iso(request.requested_at),
    }


@router.get("/deletion-requests")
async def list_deletion_requests(
    status: str = Query("pending"),
    page: int = Query(1),
    pageSize: int = Query(20),
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if status not in ("pending", "processed"):
        raise AppError(
            400, "invalid_query", "Parámetros de filtro o paginación inválidos."
        )
    pagination: Pagination = pagination_params(page, pageSize)
    base = select(DeletionRequest).where(
        DeletionRequest.client_id == principal.client_id,
        DeletionRequest.status == status,
    )
    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    rows = (
        await db.scalars(
            base.order_by(DeletionRequest.requested_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).all()
    return {
        "items": [
            {
                "requestId": str(r.id),
                "userRef": f"usr-{str(r.subject_user_id)[:8]}",
                "sessionId": str(r.session_id) if r.session_id else None,
                "requestedAt": iso(r.requested_at),
                "status": r.status,
            }
            for r in rows
        ],
        "total": total,
    }


@router.post("/deletion-requests/{request_id}/process")
async def process_deletion_request(
    request_id: str,
    principal: Principal = Depends(require_roles("client_admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rid = to_uuid(request_id, "request_not_found")
    request = await db.get(DeletionRequest, rid)
    if request is None or request.client_id != principal.client_id:
        raise AppError(404, "request_not_found", "La solicitud no existe.")
    if request.status == "processed":
        raise AppError(409, "already_processed", "La solicitud ya fue atendida.")

    storage = get_storage()
    stmt = (
        select(Recording)
        .join(PracticeSession, Recording.session_id == PracticeSession.id)
        .where(
            PracticeSession.user_id == request.subject_user_id,
            Recording.status != "deleted",
        )
    )
    if request.session_id is not None:
        stmt = stmt.where(Recording.session_id == request.session_id)
    recordings = (await db.scalars(stmt)).all()
    for recording in recordings:
        recording.status = "deleted"
        recording.deleted_at = utcnow()
        storage.delete(recording.blob_path)
        audit(
            db,
            "recording_deleted",
            actor_user_id=principal.user_id,
            client_id=principal.client_id,
            entity_type="recording",
            entity_id=recording.id,
            detail={"deletionRequestId": str(request.id)},
        )

    request.status = "processed"
    request.processed_at = utcnow()
    request.processed_by = principal.user_id
    audit(
        db,
        "deletion_processed",
        actor_user_id=principal.user_id,
        client_id=principal.client_id,
        entity_type="deletion_request",
        entity_id=request.id,
        detail={"recordingsDeleted": len(recordings)},
    )
    await db.commit()
    return {
        "requestId": str(request.id),
        "status": "processed",
        "processedAt": iso(request.processed_at),
    }
