"""FastAPI router for real-time turn submission, follow-up evaluation, and async ASR."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from . import store
from .audio_background import schedule_turn_audio_background
from .config import InterviewLiveSettings, get_settings
from .context_cache import SessionContextCache
from .gemini_followup import GeminiFollowUpService
from .schemas import SessionTurnItem, SessionTurnsListResponse, TurnSubmissionResponse

logger = logging.getLogger("interview_live.router")

ALLOWED_AUDIO_MIME_PREFIXES = (
    "audio/webm",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "video/webm",
    "application/octet-stream",
)


def create_interview_live_router(
    *,
    sql_conn_str_getter: Callable[[], str],
    verify_token_dep: Callable,
    require_session_access_fn: Callable,
    settings_getter: Callable[[], InterviewLiveSettings] = get_settings,
    context_cache: SessionContextCache | None = None,
    followup_service_factory: Callable[[InterviewLiveSettings], GeminiFollowUpService] | None = None,
) -> APIRouter:
    """Build decoupled APIRouter mountable in backend/main.py or standalone service."""
    router = APIRouter(tags=["interview-live"])
    cache = context_cache or SessionContextCache()

    def _build_followup_service(settings: InterviewLiveSettings) -> GeminiFollowUpService:
        if followup_service_factory is not None:
            return followup_service_factory(settings)
        return GeminiFollowUpService(settings=settings)

    @router.post(
        "/interview-live/sessions/{session_id}/turns",
        response_model=TurnSubmissionResponse,
    )
    @router.post(
        "/v1/interview-live/sessions/{session_id}/turns",
        response_model=TurnSubmissionResponse,
    )
    async def submit_interview_turn(
        session_id: str,
        audio: UploadFile = File(...),
        baseSequenceNo: int = Form(..., ge=1),
        turnIndex: int = Form(..., ge=1),
        turnKind: Literal["base", "follow_up"] = Form("base"),
        questionText: str = Form(..., min_length=1, max_length=2000),
        parentTurnId: str | None = Form(None),
        startOffsetMs: int | None = Form(None, ge=0),
        endOffsetMs: int | None = Form(None, ge=0),
        user: dict = Depends(verify_token_dep),
    ) -> TurnSubmissionResponse:
        sql_conn_str = sql_conn_str_getter()
        if not sql_conn_str:
            raise HTTPException(status_code=503, detail="Azure SQL no está configurado.")

        settings = settings_getter()

        # 1. Validar propiedad y estado activo de la sesión
        access = await asyncio.to_thread(
            require_session_access_fn, sql_conn_str, user, session_id
        )
        internal_session_id = str(access["id"])
        session_status = str(access.get("status") or "").lower()
        if session_status not in ("created", "consented"):
            raise HTTPException(
                status_code=409,
                detail="La sesión ya no acepta nuevos turnos de entrevista.",
            )

        # 2. Validar tipo MIME y tamaño del audio recibido
        content_type = (audio.content_type or "audio/webm").strip().lower()
        if not any(content_type.startswith(prefix) for prefix in ALLOWED_AUDIO_MIME_PREFIXES):
            raise HTTPException(
                status_code=415,
                detail=f"Formato de audio no soportado: {content_type}",
            )

        audio_bytes = await audio.read(settings.max_audio_bytes + 1)
        if len(audio_bytes) > settings.max_audio_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"El audio del turno excede el límite permitido ({settings.max_audio_bytes // (1024 * 1024)} MB).",
            )

        # 3. Cargar contexto inmutable de la sesión desde caché TTL / SQL
        try:
            ctx = await asyncio.to_thread(
                cache.get_or_load, sql_conn_str, internal_session_id
            )
        except LookupError as err:
            raise HTTPException(status_code=404, detail=str(err)) from None

        # 4. Verificar idempotencia por (session_id, turn_index) antes de invocar Gemini/ASR
        existing = await asyncio.to_thread(
            store.get_turn_by_index, sql_conn_str, internal_session_id, turnIndex
        )
        if existing is not None:
            used_followups = await asyncio.to_thread(
                store.count_followups_generated_for_base,
                sql_conn_str,
                internal_session_id,
                baseSequenceNo,
            )
            remaining = max(0, ctx.policy.max_per_base_question - used_followups)
            return TurnSubmissionResponse(
                turnId=existing["turnId"],
                sessionId=session_id,
                turnIndex=existing["turnIndex"],
                baseSequenceNo=existing["baseSequenceNo"],
                turnKind=existing["turnKind"],
                hasFollowUp=bool(existing["followupGenerated"] and existing["followupQuestionText"]),
                followUpQuestion=existing["followupQuestionText"],
                triggerReason=existing["followupTriggerReason"],
                remainingFollowUpsForBase=remaining,
                asrStatus=existing["asrStatus"],
                degraded=False,
                geminiLatencyMs=existing["geminiLatencyMs"],
                idempotentReplay=True,
            )

        # Resolver session_question_id de la pregunta base correspondiente
        base_q = next(
            (q for q in ctx.base_questions if int(q["sequenceNo"]) == int(baseSequenceNo)),
            None,
        )
        session_question_id = base_q["sessionQuestionId"] if base_q else None

        # Consultar estado mutable de turnos en SQL (multi-réplica seguro)
        prior_turns = await asyncio.to_thread(
            store.list_session_turns, sql_conn_str, internal_session_id
        )
        used_followups_for_base = sum(
            1
            for t in prior_turns
            if t["baseSequenceNo"] == baseSequenceNo
            and (t["turnKind"] == "follow_up" or t["followupGenerated"])
        )
        followup_depth = (
            1
            if turnKind == "follow_up"
            else 0
        )

        # 5. Persistir turno en dbo.session_turn (asr_status='pending')
        turn_id, already_existed = await asyncio.to_thread(
            store.create_turn,
            sql_conn_str,
            session_id=internal_session_id,
            session_question_id=session_question_id,
            parent_turn_id=parentTurnId,
            base_sequence_no=baseSequenceNo,
            turn_index=turnIndex,
            followup_depth=followup_depth,
            turn_kind=turnKind,
            question_text=questionText.strip(),
            start_offset_ms=startOffsetMs,
            end_offset_ms=endOffsetMs,
            audio_mime_type=content_type,
            audio_bytes=len(audio_bytes),
        )
        if already_existed:
            reloaded = await asyncio.to_thread(
                store.get_turn_by_index, sql_conn_str, internal_session_id, turnIndex
            )
            if reloaded:
                return TurnSubmissionResponse(
                    turnId=reloaded["turnId"],
                    sessionId=session_id,
                    turnIndex=reloaded["turnIndex"],
                    baseSequenceNo=reloaded["baseSequenceNo"],
                    turnKind=reloaded["turnKind"],
                    hasFollowUp=bool(reloaded["followupGenerated"] and reloaded["followupQuestionText"]),
                    followUpQuestion=reloaded["followupQuestionText"],
                    triggerReason=reloaded["followupTriggerReason"],
                    remainingFollowUpsForBase=max(
                        0, ctx.policy.max_per_base_question - used_followups_for_base
                    ),
                    asrStatus=reloaded["asrStatus"],
                    degraded=False,
                    geminiLatencyMs=reloaded["geminiLatencyMs"],
                    idempotentReplay=True,
                )

        # 6. Lanzar FFmpeg + RMS VAD + NVIDIA Parakeet en segundo plano (no bloquea al vocero)
        schedule_turn_audio_background(
            conn_str=sql_conn_str,
            settings=settings,
            turn_id=turn_id,
            session_id=internal_session_id,
            session_question_id=session_question_id,
            base_sequence_no=baseSequenceNo,
            turn_kind=turnKind,
            audio_bytes=audio_bytes,
            audio_mime_type=content_type,
        )

        # 7. Evaluar contrapregunta solo si la política de dificultad y cuota lo permiten
        can_ask_followup = (
            ctx.policy.enabled
            and turnKind == "base"
            and used_followups_for_base < ctx.policy.max_per_base_question
        )

        if not can_ask_followup:
            return TurnSubmissionResponse(
                turnId=turn_id,
                sessionId=session_id,
                turnIndex=turnIndex,
                baseSequenceNo=baseSequenceNo,
                turnKind=turnKind,
                hasFollowUp=False,
                followUpQuestion=None,
                triggerReason=None,
                remainingFollowUpsForBase=max(
                    0, ctx.policy.max_per_base_question - used_followups_for_base
                ),
                asrStatus="pending",
                degraded=False,
                geminiLatencyMs=0,
            )

        followup_svc = _build_followup_service(settings)
        eval_res = await followup_svc.evaluate_turn_audio(
            ctx=ctx,
            current_question=questionText.strip(),
            audio_bytes=audio_bytes,
            mime_type=content_type,
            previous_turns=prior_turns,
            current_base_sequence_no=baseSequenceNo,
        )

        await asyncio.to_thread(
            store.update_turn_followup,
            sql_conn_str,
            turn_id=turn_id,
            has_followup=eval_res.has_follow_up,
            followup_question=eval_res.follow_up_question,
            trigger_reason=eval_res.trigger_reason,
            gemini_latency_ms=eval_res.latency_ms,
        )

        new_used = used_followups_for_base + (1 if eval_res.has_follow_up else 0)
        remaining_after = max(0, ctx.policy.max_per_base_question - new_used)

        logger.info(
            "Turno en vivo procesado: session=%s turn=%d base=%d diff=%s bytes=%d hasFollowUp=%s degraded=%s geminiMs=%d",
            internal_session_id,
            turnIndex,
            baseSequenceNo,
            ctx.difficulty,
            len(audio_bytes),
            eval_res.has_follow_up,
            eval_res.degraded,
            eval_res.latency_ms,
        )

        return TurnSubmissionResponse(
            turnId=turn_id,
            sessionId=session_id,
            turnIndex=turnIndex,
            baseSequenceNo=baseSequenceNo,
            turnKind=turnKind,
            hasFollowUp=eval_res.has_follow_up,
            followUpQuestion=eval_res.follow_up_question,
            triggerReason=eval_res.trigger_reason,
            remainingFollowUpsForBase=remaining_after,
            asrStatus="pending",
            degraded=eval_res.degraded,
            geminiLatencyMs=eval_res.latency_ms,
        )

    @router.get(
        "/interview-live/sessions/{session_id}/turns",
        response_model=SessionTurnsListResponse,
    )
    @router.get(
        "/v1/interview-live/sessions/{session_id}/turns",
        response_model=SessionTurnsListResponse,
    )
    async def list_interview_turns(
        session_id: str,
        user: dict = Depends(verify_token_dep),
    ) -> SessionTurnsListResponse:
        sql_conn_str = sql_conn_str_getter()
        if not sql_conn_str:
            raise HTTPException(status_code=503, detail="Azure SQL no está configurado.")

        access = await asyncio.to_thread(
            require_session_access_fn, sql_conn_str, user, session_id, read_only=True
        )
        internal_session_id = str(access["id"])
        rows = await asyncio.to_thread(
            store.list_session_turns, sql_conn_str, internal_session_id
        )
        items = [SessionTurnItem(**r) for r in rows]
        return SessionTurnsListResponse(sessionId=session_id, turns=items)

    return router
