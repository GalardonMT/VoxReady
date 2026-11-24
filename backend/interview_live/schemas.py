"""Pydantic V2 schemas for the live turn-based interview API and Gemini output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FollowUpPolicyPayload(BaseModel):
    difficulty: Literal["basic", "intermediate", "hard"] = "intermediate"
    enabled: bool = True
    maxPerBaseQuestion: int = 1
    pressureLevel: str = "moderate"


FollowUpTriggerReason = Literal[
    "evasion_nucleo",
    "respuesta_vaga_incompleta",
    "contradiccion_interna",
    "flanco_linea_roja",
    "infraccion_linea_roja",
    "omision_impacto_o_accion",
]

_TRIGGER_REASON_ALIASES: dict[str, FollowUpTriggerReason] = {
    "evasion_nucleo": "evasion_nucleo",
    "evasion": "evasion_nucleo",
    "evasión": "evasion_nucleo",
    "respuesta_vaga_incompleta": "respuesta_vaga_incompleta",
    "respuesta_vaga": "respuesta_vaga_incompleta",
    "vaga": "respuesta_vaga_incompleta",
    "incompleta": "respuesta_vaga_incompleta",
    "contradiccion_interna": "contradiccion_interna",
    "contradiccion": "contradiccion_interna",
    "contradicción": "contradiccion_interna",
    "flanco_linea_roja": "flanco_linea_roja",
    "presion_linea_roja": "flanco_linea_roja",
    "linea_roja": "flanco_linea_roja",
    "infraccion_linea_roja": "infraccion_linea_roja",
    "vulneracion_linea_roja": "infraccion_linea_roja",
    "omision_impacto_o_accion": "omision_impacto_o_accion",
    "falta_mensaje_clave": "omision_impacto_o_accion",
    "omision_mensaje_clave": "omision_impacto_o_accion",
}


def _trim_complete_question(text: str, max_chars: int = 240) -> str:
    """Ensure TTS-safe question length without cutting mid-sentence with ellipsis."""
    if len(text) <= max_chars:
        return text
    window = text[:max_chars].rstrip()
    for punct in ("?", ".", "!"):
        idx = window.rfind(punct)
        if idx >= 15:
            return window[: idx + 1].strip()
    space_idx = window.rfind(" ")
    trimmed = window[:space_idx].rstrip(" ,;:-") if space_idx >= 15 else window.rstrip(" ,;:-")
    if not trimmed.endswith("?"):
        if trimmed and not trimmed.startswith("¿"):
            trimmed = f"¿{trimmed[0].upper()}{trimmed[1:]}"
        trimmed = f"{trimmed}?"
    return trimmed


def _normalize_trigger_reason(raw_reason: Any) -> FollowUpTriggerReason | None:
    if raw_reason is None:
        return None
    cleaned = str(raw_reason).strip().lower()
    if not cleaned or cleaned in {"null", "none", "n/a"}:
        return None
    if cleaned in _TRIGGER_REASON_ALIASES:
        return _TRIGGER_REASON_ALIASES[cleaned]
    if "infracc" in cleaned or "vulner" in cleaned:
        return "infraccion_linea_roja"
    if "roja" in cleaned or "flanco" in cleaned:
        return "flanco_linea_roja"
    if "contradic" in cleaned:
        return "contradiccion_interna"
    if "evas" in cleaned or "desvi" in cleaned:
        return "evasion_nucleo"
    if "mensaje" in cleaned or "afectad" in cleaned or "omisi" in cleaned:
        return "omision_impacto_o_accion"
    return "respuesta_vaga_incompleta"


class GeminiFollowUpDecision(BaseModel):
    hasFollowUp: bool = Field(
        default=False,
        description="True solo si corresponde formular una contrapregunta incisiva según la política activa.",
    )
    followUpQuestion: str | None = Field(
        default=None,
        description="1 sola pregunta periodística completa en español para lectura en voz alta (25 a 220 caracteres).",
    )
    triggerReason: FollowUpTriggerReason | None = Field(
        default=None,
        description=(
            "Código canónico del motivo editorial: evasion_nucleo, respuesta_vaga_incompleta, "
            "contradiccion_interna, flanco_linea_roja, infraccion_linea_roja u omision_impacto_o_accion."
        ),
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
        if q_clean:
            q_clean = _trim_complete_question(q_clean, max_chars=240)

        reason_raw = data.get("triggerReason")
        if reason_raw is None and "trigger_reason" in data:
            reason_raw = data.get("trigger_reason")
        reason_clean = _normalize_trigger_reason(reason_raw)

        if not has_fu_bool or len(q_clean) < 10:
            return {
                "hasFollowUp": False,
                "followUpQuestion": None,
                "triggerReason": None,
            }

        return {
            "hasFollowUp": True,
            "followUpQuestion": q_clean,
            "triggerReason": reason_clean or "respuesta_vaga_incompleta",
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
