"""FastAPI adapter for the master labeling queue.

Authentication, database access and Blob SAS issuance are injected so this
module remains contract-testable without Azure credentials.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

try:
    import labeling_store
    from schemas.labeling import (
        LabelingCaseDetail, LabelingCaseList, LeaseRequest, LeaseResponse,
        ProblemDetails, QualitySummaryResponse, RecordingUrlResponse,
        ReleaseLeaseRequest, ReviewListResponse, ReviewRequest, ReviewResponse,
    )
except ImportError:
    from backend import labeling_store
    from backend.schemas.labeling import (
        LabelingCaseDetail, LabelingCaseList, LeaseRequest, LeaseResponse,
        ProblemDetails, QualitySummaryResponse, RecordingUrlResponse,
        ReleaseLeaseRequest, ReviewListResponse, ReviewRequest, ReviewResponse,
    )


PROBLEM_BASE = "https://voxready.example/problems/"
ERROR_TITLES = {
    403: "Acceso denegado", 404: "Recurso no encontrado",
    409: "Conflicto de estado", 410: "Grabación no disponible",
    422: "Solicitud inválida", 503: "Servicio no disponible",
}
ERROR_RESPONSES = {
    status: {"model": ProblemDetails, "content": {"application/problem+json": {}}}
    for status in (403, 404, 409, 410, 422, 503)
}


class LabelingProblem(Exception):
    def __init__(self, status: int, code: str, detail: str, context=None):
        self.status = status
        self.code = code
        self.detail = detail
        self.context = context or None


def _problem_response(request: Request, status: int, code: str, detail: str, context=None):
    correlation = request.headers.get("x-correlation-id")
    try:
        correlation = str(uuid.UUID(str(correlation)))
    except (TypeError, ValueError, AttributeError):
        correlation = str(uuid.uuid4())
    body = {
        "type": PROBLEM_BASE + code.lower().replace("_", "-"),
        "title": ERROR_TITLES.get(status, "Error"),
        "status": status,
        "detail": detail,
        "code": code,
        "correlationId": correlation,
    }
    if context:
        body["context"] = _utc_values(context)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


class LabelingRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError as error:
                fields = [
                    {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
                    for item in error.errors()
                ]
                return _problem_response(request, 422, "VALIDATION_ERROR", "La solicitud no cumple el contrato.", {"fieldErrors": fields})
            except labeling_store.LabelingStoreError as error:
                return _problem_response(request, error.status, error.code, str(error), error.context)
            except LabelingProblem as error:
                return _problem_response(request, error.status, error.code, error.detail, error.context)
            except HTTPException as error:
                code = {403: "MASTER_ROLE_REQUIRED", 404: "NOT_FOUND", 409: "CONFLICT", 410: "GONE", 422: "VALIDATION_ERROR", 503: "DEPENDENCY_UNAVAILABLE"}.get(error.status_code, "REQUEST_FAILED")
                return _problem_response(request, error.status_code, code, str(error.detail))

        return handler


def _utc_values(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _utc_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_utc_values(item) for item in value]
    return value


def _get_recording_evidence(cursor, case_id):
    cursor.execute(
        """/* labeling:recording:evidence */
        SELECT id,client_id,recording_evidence_path,recording_version_id,
               recording_etag,recording_content_type,recording_duration_seconds
          FROM dbo.labeling_case WHERE id=?""",
        str(case_id),
    )
    row = cursor.fetchone()
    if not row:
        raise labeling_store.LabelingStoreError("CASE_NOT_FOUND", "Caso no encontrado.", status=404)
    evidence = {
        "caseId": str(row[0]), "clientId": str(row[1]), "path": row[2],
        "versionId": row[3], "etag": row[4], "contentType": row[5],
        "durationSeconds": float(row[6]) if row[6] is not None else None,
    }
    if not all(evidence.get(key) for key in ("path", "etag", "contentType")):
        raise labeling_store.LabelingStoreError(
            "RECORDING_RETAINED_OR_DELETED", "La grabación sellada ya no está disponible.",
            status=410, context={"retentionState": "unavailable"},
        )
    return evidence


def create_labeling_router(*, verify_token_dependency, database_factory,
                           resolve_master, issue_recording_url, api_enabled=lambda: True):
    def require_master_config(request: Request, claims=Depends(verify_token_dependency)):
        if not api_enabled():
            raise LabelingProblem(503, "LABELING_API_DISABLED", "La cola de etiquetado no está habilitada.")
        with database_factory() as cursor:
            profile = resolve_master(cursor, claims)
        if profile.get("role") != "master_config":
            raise LabelingProblem(403, "MASTER_ROLE_REQUIRED", "Se requiere el rol master_config.")
        request.state.labeling_master = profile
        return profile

    router = APIRouter(
        route_class=LabelingRoute,
        tags=["master-labeling"],
        dependencies=[Depends(require_master_config)],
    )

    def paths(path):
        return (path, "/v1" + path)

    for path in paths("/api/master/labeling-cases"):
        router.add_api_route(path, _list_cases, methods=["GET"], response_model=LabelingCaseList, responses=ERROR_RESPONSES)
    for path in paths("/api/master/labeling-cases/{case_id}"):
        router.add_api_route(path, _case_detail, methods=["GET"], response_model=LabelingCaseDetail, responses=ERROR_RESPONSES)
    for path in paths("/api/master/labeling-cases/{case_id}/lease"):
        router.add_api_route(path, _acquire_lease, methods=["POST"], response_model=LeaseResponse, responses=ERROR_RESPONSES)
        router.add_api_route(path, _release_lease, methods=["DELETE"], status_code=204, response_model=None, responses=ERROR_RESPONSES)
    for path in paths("/api/master/labeling-cases/{case_id}/recording-url"):
        router.add_api_route(path, _recording_url, methods=["GET"], response_model=RecordingUrlResponse, responses=ERROR_RESPONSES)
    for path in paths("/api/master/labeling-cases/{case_id}/reviews"):
        router.add_api_route(path, _submit_review, methods=["POST"], response_model=ReviewResponse, status_code=201, responses={200: {"model": ReviewResponse}, **ERROR_RESPONSES})
        router.add_api_route(path, _list_reviews, methods=["GET"], response_model=ReviewListResponse, responses=ERROR_RESPONSES)
    for path in paths("/api/master/quality-reviews/summary"):
        router.add_api_route(path, _quality_summary, methods=["GET"], response_model=QualitySummaryResponse, responses=ERROR_RESPONSES)

    global _LABELING_DB, _LABELING_RECORDING_URL
    _LABELING_DB = database_factory
    _LABELING_RECORDING_URL = issue_recording_url
    return router


_LABELING_DB = None
_LABELING_RECORDING_URL = None


def _actor(profile):
    return profile["id"]


def _authorized(request: Request):
    profile = getattr(request.state, "labeling_master", None)
    if profile is None:
        raise LabelingProblem(403, "MASTER_ROLE_REQUIRED", "Se requiere el rol master_config.")
    return profile


def _list_cases(request: Request, status: str = Query("pending", pattern="^(pending|reviewed)$"), limit: int = Query(10, ge=1, le=10)):
    profile = _authorized(request)
    with _LABELING_DB() as cursor:
        return labeling_store.list_cases(cursor, status=status, limit=limit, actor_id=_actor(profile))


def _case_detail(case_id: uuid.UUID, request: Request):
    profile = _authorized(request)
    with _LABELING_DB() as cursor:
        return labeling_store.get_case_detail(cursor, case_id, actor_id=_actor(profile))


def _acquire_lease(case_id: uuid.UUID, payload: LeaseRequest, request: Request):
    profile = _authorized(request)
    with _LABELING_DB() as cursor:
        return labeling_store.acquire_lease(
            cursor,
            case_id,
            _actor(profile),
            lease_token=payload.leaseToken,
            lease_generation=payload.leaseGeneration,
            allow_reviewed=True,
        )


def _release_lease(case_id: uuid.UUID, payload: ReleaseLeaseRequest, request: Request):
    profile = _authorized(request)
    with _LABELING_DB() as cursor:
        labeling_store.release_lease(cursor, case_id, _actor(profile), lease_token=payload.leaseToken, lease_generation=payload.leaseGeneration)
    return Response(status_code=204)


def _recording_url(case_id: uuid.UUID, request: Request):
    profile = _authorized(request)
    with _LABELING_DB() as cursor:
        evidence = _get_recording_evidence(cursor, case_id)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    try:
        url = _LABELING_RECORDING_URL(evidence, expires_at)
    except LabelingProblem:
        raise
    except Exception as error:
        if error.__class__.__name__ in {"ResourceNotFoundError", "BlobNotFound"}:
            raise LabelingProblem(410, "RECORDING_RETAINED_OR_DELETED", "La grabación sellada ya no está disponible.", {"retentionState": "deleted"}) from None
        raise LabelingProblem(503, "STORAGE_UNAVAILABLE", "No se pudo emitir acceso temporal a la grabación.") from None
    with _LABELING_DB() as cursor:
        labeling_store.audit_recording_access(cursor, case_id=case_id, client_id=evidence["clientId"], actor_id=_actor(profile), version_id=evidence["versionId"])
    return JSONResponse(_utc_values({
        "url": url, "expiresAt": expires_at, "contentType": evidence["contentType"],
        "durationSeconds": evidence["durationSeconds"], "etag": evidence["etag"],
        "blobVersionId": evidence["versionId"],
    }), headers={"Cache-Control": "no-store"})


def _submit_review(case_id: uuid.UUID, payload: ReviewRequest, request: Request, response: Response):
    profile = _authorized(request)
    with _LABELING_DB() as cursor:
        result = labeling_store.submit_review(cursor, case_id, _actor(profile), payload)
    response.status_code = 200 if result["replayed"] else 201
    return result["review"]


def _list_reviews(case_id: uuid.UUID, request: Request):
    _authorized(request)
    with _LABELING_DB() as cursor:
        return labeling_store.list_reviews(cursor, case_id)


def _quality_summary(request: Request, period_from: datetime | None = Query(None, alias="from"), period_to: datetime | None = Query(None, alias="to"), current_reviews_only: bool = Query(True, alias="currentReviewsOnly")):
    _authorized(request)
    with _LABELING_DB() as cursor:
        return labeling_store.quality_summary(cursor, period_from=period_from, period_to=period_to, current_reviews_only=current_reviews_only)
