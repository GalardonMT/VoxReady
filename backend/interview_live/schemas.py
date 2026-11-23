"""Pydantic V2 schemas for the live turn-based interview API and Gemini output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FollowUpPolicyPayload(BaseModel):
    difficulty: Literal["basic", "intermediate", "hard"] = "intermediate"
    enabled: bool = True
    maxPerBaseQuestion: int = 1
    pressureLevel: str = "moderate"


class GeminiFollowUpDecision(BaseModel):
    hasFollowUp: bool = Field(
        default=False,
        description="True solo si corresponde formular una contrapregunta incisiva.",
    )
    followUpQuestion: str | None = Field(
        default=None,
        description="Contrapregunta breve y directa en español (1-2 oraciones, máx 260 caracteres).",
    )
    triggerReason: str | None = Field(
        default=None,
        description="Motivo editorial breve (evasion, falta_mensaje_clave, presion_linea_roja, contradiccion).",
    )

    @model_validator(mode="before")
    @classmethod
    def sanitize_decision(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"hasFollowUp": False, "followUpQuestion": None, "triggerReason": None}

        has_fu = data.get("hasFollowUp")
        if has_fu is None and "has_follow_up" in data:
            has_fu = data.get("has_follow_up")
        if isinstance(has_fu, str):
            has_fu = has_fu.strip().lower() in {"true", "1", "yes", "si", "sí"}
        has_fu_bool = bool(has_fu)

        q_raw = data.get("followUpQuestion")
        if q_raw is None and "follow_up_question" in data:
            q_raw = data.get("follow_up_question")
        q_clean = str(q_raw).strip() if q_raw is not None else ""
        if q_clean.lower() in {"null", "none", "n/a", ""}:
            q_clean = ""
        if len(q_clean) > 320:
            q_clean = q_clean[:317].rstrip() + "..."

        reason_raw = data.get("triggerReason")
        if reason_raw is None and "trigger_reason" in data:
            reason_raw = data.get("trigger_reason")
        reason_clean = str(reason_raw).strip()[:480] if reason_raw is not None else None
        if reason_clean and reason_clean.lower() in {"null", "none", ""}:
            reason_clean = None

        if not has_fu_bool or len(q_clean) < 10:
            return {
                "hasFollowUp": False,
                "followUpQuestion": None,
                "triggerReason": reason_clean if has_fu_bool else None,
            }

        return {
            "hasFollowUp": True,
            "followUpQuestion": q_clean,
            "triggerReason": reason_clean,
        }


class TurnSubmissionResponse(BaseModel):
    turnId: str
    sessionId: str
    turnIndex: int
    baseSequenceNo: int
    turnKind: Literal["base", "follow_up"]
    hasFollowUp: bool
    followUpQuestion: str | None = None
    triggerReason: str | None = None
    remainingFollowUpsForBase: int = 0
    asrStatus: str = "pending"
    degraded: bool = False
    geminiLatencyMs: int | None = None
    idempotentReplay: bool = False


class SessionTurnItem(BaseModel):
    turnId: str
    sessionId: str
    baseSequenceNo: int
    turnIndex: int
    followupDepth: int
    turnKind: Literal["base", "follow_up"]
    parentTurnId: str | None = None
    questionText: str
    followupGenerated: bool = False
    followupQuestionText: str | None = None
    followupTriggerReason: str | None = None
    startOffsetMs: int | None = None
    endOffsetMs: int | None = None
    audioDurationSec: float | None = None
    speechTimeSec: float | None = None
    phonationRatio: float | None = None
    transcript: str | None = None
    asrStatus: str
    geminiLatencyMs: int | None = None
    ffmpegLatencyMs: int | None = None
    parakeetLatencyMs: int | None = None


class SessionTurnsListResponse(BaseModel):
    sessionId: str
    turns: list[SessionTurnItem]
