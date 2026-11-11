import os
import re
import json
import time
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI

logger = logging.getLogger("ca-backend-api.ai-inference")


class FollowUpInput(BaseModel):
    currentQuestion: str = Field(..., min_length=5, description="Pregunta formulada en el turno actual")
    userAnswerTranscript: str = Field(..., min_length=10, description="Transcripción de la respuesta del vocero")
    topicContext: str = Field(..., min_length=5, description="Contexto del escenario o crisis")
    topicRedLines: List[str] = Field(default_factory=list, description="Líneas rojas corporativas no transgredibles")
    keyMessages: List[str] = Field(default_factory=list, description="Mensajes clave institucionales requeridos")


class FollowUpResponse(BaseModel):
    followUpQuestion: str = Field(..., description="Contrapregunta periodística incisiva y desafiante")
    rationale: str = Field(..., description="Justificación editorial de la contrapregunta")
    targetRisk: str = Field(..., description="Riesgo comunicacional o legal que se busca auditar")


class AiInferenceService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        fast_model: Optional[str] = None,
        timeout: float = 15.0,
    ):
        raw_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("NVIDIA_API_KEY") or ""
        self.api_key = raw_key.strip()

        raw_base = (
            base_url
            or os.getenv("GEMINI_OPENAI_BASE_URL")
            or "https://generativelanguage.googleapis.com/v1beta/openai/"
        ).strip()
        # Regla crítica: Base URL de Google OpenAI compatibility endpoint debe terminar en '/'
        if "generativelanguage.googleapis.com" in raw_base and not raw_base.endswith("/"):
            raw_base += "/"
        elif raw_base.endswith("/chat/completions"):
            raw_base = raw_base[:-len("/chat/completions")].rstrip("/")
        self.base_url = raw_base

        self.fast_model = fast_model or os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
        self.timeout = timeout
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            import httpx
            http_client = httpx.Client(verify=False, timeout=self.timeout)
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                http_client=http_client,
            )
        return self._client

    def generate_dynamic_follow_up(self, payload: FollowUpInput) -> FollowUpResponse:
        """
        Genera una contrapregunta periodística dinámica utilizando gemini-3.5-flash-lite
        con reasoning_effort='low' para minimizar la latencia interactiva (<1s).
        """
        red_lines_str = "\n".join(f"- {rl}" for rl in payload.topicRedLines) if payload.topicRedLines else "Ninguna especificada."
        messages_str = "\n".join(f"- {m}" for m in payload.keyMessages) if payload.keyMessages else "Ninguno especificado."

        system_prompt = (
            "Eres un periodista de investigación incisivo en una rueda de prensa de alta tensión. "
            "Tu tarea es escuchar la respuesta del vocero, identificar inconsistencias, evasiones o falta de precisión, "
            "y formular una contrapregunta directa, difícil y profesional (máximo 30 palabras). "
            "Responde estrictamente en formato JSON conforme al esquema solicitado."
        )

        user_content = f"""Contexto de crisis:
{payload.topicContext}

Líneas rojas del escenario (si las vulnera o evade, presiónalo en ese punto):
{red_lines_str}

Mensajes clave institucionales:
{messages_str}

Pregunta previa formulada:
\"{payload.currentQuestion}\"

Respuesta ofrecida por el vocero:
\"{payload.userAnswerTranscript}\"

Formula una contrapregunta periodística punzante que ponga a prueba al vocero."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Intentar 2 veces con backoff breve
        for attempt in range(1, 3):
            try:
                completion = self.client.beta.chat.completions.parse(
                    model=self.fast_model,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=150,
                    response_format=FollowUpResponse,
                    extra_body={"reasoning_effort": "low"},
                    timeout=self.timeout,
                )
                parsed = completion.choices[0].message.parsed
                if parsed:
                    return parsed
            except Exception as e:
                logger.error(f"[AiInference] Error generando follow-up con {self.fast_model}: {e}")
                if attempt == 1:
                    time.sleep(1.0)
                    continue

        # Fallback determinista en caso de indisponibilidad de API
        logger.warning("[AiInference] Activando contrapregunta de fallback determinista por falla en API.")
        return FollowUpResponse(
            followUpQuestion="Teniendo en cuenta el contexto del incidente y su respuesta previa, ¿qué garantías operativas inmediatas y verificables puede ofrecer en este momento?",
            rationale="Contrapregunta predeterminada de control por contingencia de servicio de inferencia.",
            targetRisk="Evasión de compromisos concretos y falta de certidumbre operativa.",
        )


_service_instance: Optional[AiInferenceService] = None


def get_ai_inference_service() -> AiInferenceService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AiInferenceService()
    return _service_instance

