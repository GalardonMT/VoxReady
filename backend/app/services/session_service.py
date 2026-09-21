"""Session flow service: creation, consent, recording URL, finish, report."""
import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.errors import AppError
from app.core.security import Principal
from app.core.storage import StorageService
from app.models.analysis import AnalysisJob, AnalysisPipelineResult, AreaScore, Report
from app.models.content import Question, Scenario, Topic
from app.models.recording import Recording
from app.models.sessions import (
    Consent,
    IdempotencyKey,
    PracticeSession,
    SessionQuestion,
)
from app.schemas.sessions import ConsentIn, SessionCreateIn
from app.services.helpers import audit, get_current_policy, get_current_rubric
from app.utils import ALLOWED_RECORDING_MIME, LANGUAGES, PIPELINES, iso, utcnow


def to_uuid(value: str, error_code: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise AppError(404, error_code, "El recurso indicado no existe.")


async def get_own_session(
    db: AsyncSession, principal: Principal, session_id: str
) -> PracticeSession:
    sid = to_uuid(session_id, "session_not_found")
    session = await db.get(PracticeSession, sid)
    if (
        session is None
        or session.is_deleted
        or session.user_id != principal.user_id
    ):
        raise AppError(
            404, "session_not_found", "La sesión no existe o no pertenece al usuario."
        )
    return session


async def _pick_questions(
    db: AsyncSession,
    scenario: Scenario,
    client_id: uuid.UUID,
    language: str,
) -> list[Question]:
    """Pick bank questions for the scenario; top-up with AI-generated ones."""
    rows = list(
        (
            await db.scalars(
                select(Question)
                .where(
                    Question.topic_id == scenario.topic_id,
                    Question.client_id == client_id,
                    Question.in_bank.is_(True),
                    Question.status == "active",
                    Question.is_deleted.is_(False),
                )
                .order_by(Question.created_at)
                .limit(scenario.question_count)
            )
        ).all()
    )
    missing = scenario.question_count - len(rows)
    if missing > 0:
        topic = await db.get(Topic, scenario.topic_id)
        topic_name = topic.name if topic else "el tema"
        for i in range(missing):
            question = Question(
                client_id=client_id,
                topic_id=scenario.topic_id,
                text=(
                    f"Pregunta generada por IA sobre '{topic_name}' "
                    f"#{len(rows) + i + 1}: ¿cómo respondería ante los medios?"
                ),
                source="ai",
                base_language=language,
                rating_count=0,
                in_bank=True,
                status="active",
            )
            db.add(question)
            rows.append(question)
    return rows


async def create_session(
    db: AsyncSession,
    principal: Principal,
    body: SessionCreateIn,
    idempotency_key: str | None,
) -> dict:
    if idempotency_key:
        existing = await db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.key == idempotency_key,
                IdempotencyKey.user_id == principal.user_id,
            )
        )
        if existing is not None:
            return existing.response_json

    scenario_id = to_uuid(body.scenarioId, "scenario_not_found")
    scenario = await db.get(Scenario, scenario_id)
    if (
        scenario is None
        or scenario.is_deleted
        or scenario.client_id != principal.client_id
        or scenario.status != "active"
    ):
        raise AppError(
            404,
            "scenario_not_found",
            "El escenario indicado no existe o no está disponible.",
        )

    language = body.language or principal.preferred_language
    if language not in LANGUAGES:
        raise AppError(400, "invalid_request", "Idioma no soportado.")

    rubric = await get_current_rubric(db)
    if rubric is None:
        raise AppError(
            500, "internal_error", "No hay una versión de rúbrica vigente."
        )

    session = PracticeSession(
        client_id=principal.client_id,
        user_id=principal.user_id,
        scenario_id=scenario.id,
        language=language,
        status="created",
        rubric_version_id=rubric.id,
    )
    db.add(session)
    await db.flush()

    questions = await _pick_questions(db, scenario, principal.client_id, language)
    for index, question in enumerate(questions, start=1):
        db.add(
            SessionQuestion(
                session_id=session.id,
                question_id=question.id,
                sequence_no=index,
            )
        )

    response = {
        "sessionId": str(session.id),
        "status": "created",
        "scenarioId": str(scenario.id),
        "questionCount": len(questions),
        "createdAt": iso(session.created_at),
    }
    if idempotency_key:
        db.add(
            IdempotencyKey(
                key=idempotency_key,
                user_id=principal.user_id,
                endpoint="POST /v1/sessions",
                response_json=response,
                created_at=utcnow(),
            )
        )
    await db.commit()
    return response


async def register_consent(
    db: AsyncSession,
    principal: Principal,
    session_id: str,
    body: ConsentIn,
) -> dict:
    session = await get_own_session(db, principal, session_id)
    if session.status != "created":
        raise AppError(409, "invalid_state", "La sesión no está en estado 'created'.")
    if not (body.acceptRecording and body.acknowledgeDeletion):
        raise AppError(
            400,
            "consent_incomplete",
            "No se aceptaron ambas casillas obligatorias.",
        )

    policy = await get_current_policy(db, session.client_id)
    if policy is None:
        raise AppError(
            500, "internal_error", "El cliente no tiene política de retención vigente."
        )

    consent = Consent(
        session_id=session.id,
        user_id=principal.user_id,
        accept_recording=body.acceptRecording,
        acknowledge_deletion=body.acknowledgeDeletion,
        retention_policy_id=policy.id,
        consent_hash=hashlib.sha256(
            f"{policy.version_label}:{policy.keep}".encode()
        ).hexdigest(),
        consented_at=utcnow(),
    )
    db.add(consent)
    session.status = "consented"
    audit(
        db,
        "consent_given",
        actor_user_id=principal.user_id,
        client_id=session.client_id,
        entity_type="session",
        entity_id=session.id,
        detail={"policyVersion": body.policyVersion},
    )
    await db.commit()
    return {
        "sessionId": str(session.id),
        "status": "consented",
        "consentId": str(consent.id),
        "consentedAt": iso(consent.consented_at),
    }


async def issue_recording_url(
    db: AsyncSession,
    principal: Principal,
    session_id: str,
    content_type: str,
    duration_seconds: int | None,
    base_url: str,
    storage: StorageService,
) -> dict:
    if content_type not in ALLOWED_RECORDING_MIME:
        raise AppError(400, "invalid_content_type", "MIME no soportado.")
    session = await get_own_session(db, principal, session_id)
    if session.status == "created":
        raise AppError(
            409, "consent_required", "No se puede grabar sin consentimiento previo."
        )
    if session.status not in ("consented", "recording"):
        raise AppError(
            409,
            "invalid_state",
            "La sesión no está lista para grabar.",
        )
    grant = storage.create_upload_grant(
        base_url, session.id, content_type, duration_seconds
    )
    session.status = "recording"
    if session.started_at is None:
        session.started_at = utcnow()
    await db.commit()
    return {
        "uploadUrl": grant.upload_url,
        "blobPath": grant.blob_path,
        "expiresAt": iso(grant.expires_at),
        "maxSizeBytes": grant.max_size_bytes,
    }


async def finish_session(
    db: AsyncSession,
    principal: Principal,
    session_id: str,
    blob_path: str,
    storage: StorageService,
    settings: Settings,
) -> dict:
    session = await get_own_session(db, principal, session_id)
    if session.status != "recording":
        raise AppError(
            409,
            "invalid_state",
            "La sesión no está lista para analizar (falta consentimiento o grabación).",
        )
    if not storage.exists(blob_path):
        raise AppError(
            400,
            "blob_missing",
            "El blob indicado no existe o no se terminó de subir.",
        )

    policy = await get_current_policy(db, session.client_id)
    if policy is not None and policy.keep == "full_recording":
        meta = storage.pop_pending(blob_path)
        db.add(
            Recording(
                session_id=session.id,
                blob_container="local",
                blob_path=blob_path,
                content_type=meta.get("content_type")
                or ("video/webm" if blob_path.endswith(".webm") else "video/mp4"),
                duration_seconds=meta.get("duration_seconds"),
                size_bytes=storage.size(blob_path),
                storage_tier="hot",
                status="available",
            )
        )
    else:
        storage.pop_pending(blob_path)

    job = AnalysisJob(
        session_id=session.id,
        status="queued",
        rubric_version_id=session.rubric_version_id,
        estimated_seconds=settings.analysis_estimated_seconds,
    )
    db.add(job)
    await db.flush()
    for pipeline in PIPELINES:
        db.add(
            AnalysisPipelineResult(
                analysis_job_id=job.id, pipeline=pipeline, status="pending"
            )
        )
    session.status = "analyzing"
    session.finished_at = utcnow()
    await db.commit()
    return {
        "sessionId": str(session.id),
        "status": "analyzing",
        "analysisId": str(job.id),
        "estimatedSeconds": job.estimated_seconds,
    }


async def get_analysis_status(
    db: AsyncSession, principal: Principal, session_id: str
) -> dict:
    session = await get_own_session(db, principal, session_id)
    job = await db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.session_id == session.id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        raise AppError(
            409, "invalid_state", "La sesión no tiene un análisis en curso."
        )
    rows = (
        await db.scalars(
            select(AnalysisPipelineResult).where(
                AnalysisPipelineResult.analysis_job_id == job.id
            )
        )
    ).all()
    progress = {p: "pending" for p in PIPELINES}
    for row in rows:
        progress[row.pipeline] = "done" if row.status == "done" else row.status
    return {
        "analysisId": str(job.id),
        "status": job.status,
        "progress": progress,
        "reportReady": job.status == "completed",
        "failureReason": job.failure_reason,
    }


async def get_report(
    db: AsyncSession,
    principal: Principal,
    session_id: str,
    base_url: str,
    storage: StorageService,
) -> dict:
    session = await get_own_session(db, principal, session_id)
    report = await db.scalar(
        select(Report)
        .where(Report.session_id == session.id, Report.is_current.is_(True))
        .order_by(Report.generated_at.desc())
        .limit(1)
    )
    if report is None:
        raise AppError(
            409, "report_not_ready", "El análisis aún no finaliza; reintentar más tarde."
        )

    from app.models.rubric import RubricArea

    score_rows = (
        await db.execute(
            select(AreaScore.value, RubricArea.area_key)
            .join(RubricArea, AreaScore.rubric_area_id == RubricArea.id)
            .where(AreaScore.report_id == report.id)
            .order_by(RubricArea.sort_order)
        )
    ).all()

    recording_url = None
    policy = await get_current_policy(db, session.client_id)
    recording = await db.scalar(
        select(Recording)
        .where(Recording.session_id == session.id)
        .order_by(Recording.created_at.desc())
        .limit(1)
    )
    if (
        policy is not None
        and policy.keep == "full_recording"
        and recording is not None
        and recording.status == "available"
    ):
        recording_url = storage.create_read_url(base_url, recording.blob_path)

    scenario = await db.get(Scenario, session.scenario_id)
    return {
        "sessionId": str(session.id),
        "overallScore": report.overall_score,
        "narrative": {
            "strengths": report.narrative_strengths or [],
            "improvements": report.narrative_improvements or [],
            "crossSignal": report.cross_signal_observation or "",
        },
        "areaScores": [{"area": key, "value": value} for value, key in score_rows],
        "recordingUrl": recording_url,
        "scenarioTitle": scenario.title if scenario else "",
        "generatedAt": iso(report.generated_at),
    }
