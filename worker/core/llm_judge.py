import os
import json
from typing import Dict, Any, Optional, List
from utils.logger import get_logger
from services.keyvault_service import get_secret

logger = get_logger("core.llm_judge")

DEFAULT_SYSTEM_PROMPT = """Eres un evaluador experto y juez de comunicación estratégica y manejo de crisis corporativa.
Tu tarea es calificar con rigor la respuesta y desempeño del vocero institucional a partir de la transcripción de su declaración y el contexto de la crisis.

Debes evaluar cuatro dimensiones críticas:
1. Apego a mensajes clave institucionales (Key Message Adherence).
2. Técnica de "bridging" (desvío constructivo de preguntas hostiles o especulaciones hacia los pilares de control).
3. Control emocional y de crisis (calma, firmeza, no especular, contención del pánico).
4. Consistencia y claridad narrativa corporativa.

REGLA OBLIGATORIA: Debes responder EXCLUSIVAMENTE con un objeto JSON válido con la siguiente estructura exacta:
{
  "key_message_adherence_score": <entero entre 0 y 100>,
  "crisis_control_score": <entero entre 0 y 100>,
  "bridging_detected": <booleano true/false>,
  "strengths": ["<fortaleza 1>", "<fortaleza 2>"],
  "weaknesses": ["<debilidad 1>", "<debilidad 2>"],
  "executive_summary": "<resumen ejecutivo en 1 o 2 oraciones concisas>"
}"""


class LLMJudge:
    """
    Evaluador LLM Juez para gestión de crisis corporativa utilizando
    NVIDIA Build API y el SDK oficial de OpenAI en Python.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or get_secret("NVIDIA_API_KEY")
        self.base_url = (
            base_url
            or get_secret("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        )
        self.model_name = (
            model_name
            or get_secret("LLM_MODEL_NAME", "meta/llama-3.2-90b-vision-instruct")
        )
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                logger.warning("NVIDIA_API_KEY no configurada para LLM Judge.")
                return None
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
            except Exception as e:
                logger.error(f"Error inicializando cliente OpenAI para NVIDIA Build API: {e}")
                raise
        return self._client

    def evaluate_transcript(
        self,
        transcript: str,
        crisis_context: Optional[str] = None,
        key_messages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evalúa la transcripción del vocero frente a los mensajes clave y contexto de crisis.
        """
        if not transcript or not transcript.strip():
            logger.warning("Transcripción vacía o ausente. Generando evaluación por defecto.")
            return {
                "key_message_adherence_score": 0,
                "crisis_control_score": 0,
                "bridging_detected": False,
                "strengths": [],
                "weaknesses": ["No se detectó audio ni transcripción inteligible."],
                "executive_summary": "No fue posible evaluar la declaración debido a la ausencia de contenido verbal.",
            }

        client = self._get_client()
        if client is None:
            logger.warning(
                "Sin credenciales de NVIDIA Build API. Retornando evaluación heurística simulada."
            )
            return self._heuristic_fallback(transcript)

        user_content = f"TRANSCRIPCIÓN DEL VOCERO:\n\"{transcript}\"\n\n"
        if crisis_context:
            user_content += f"CONTEXTO DE LA CRISIS:\n{crisis_context}\n\n"
        if key_messages:
            user_content += f"MENSAJES CLAVE ESPERADOS:\n- " + "\n- ".join(key_messages) + "\n\n"

        user_content += "Por favor emite tu dictamen técnico en formato JSON."

        logger.info(
            f"Enviando transcripción a NVIDIA Build API ({self.model_name}) para evaluación de crisis..."
        )

        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw_content = response.choices[0].message.content
            parsed_json = json.loads(raw_content)

            # Validar y normalizar esquema de salida requerido
            clean_result = {
                "key_message_adherence_score": int(parsed_json.get("key_message_adherence_score", 70)),
                "crisis_control_score": int(parsed_json.get("crisis_control_score", 70)),
                "bridging_detected": bool(parsed_json.get("bridging_detected", False)),
                "strengths": list(parsed_json.get("strengths", [])),
                "weaknesses": list(parsed_json.get("weaknesses", [])),
                "executive_summary": str(parsed_json.get("executive_summary", "")),
            }

            logger.info(
                f"Evaluación LLM completada: apego={clean_result['key_message_adherence_score']}, "
                f"control={clean_result['crisis_control_score']}, bridging={clean_result['bridging_detected']}."
            )
            return clean_result

        except Exception as e:
            logger.error(f"Error invocando NVIDIA Build API para LLM Judge: {e}")
            return self._heuristic_fallback(transcript, error=str(e))

    def _heuristic_fallback(
        self, transcript: str, error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fallback determinista para ambientes sin conexión externa a NVIDIA Build API."""
        words = transcript.lower().split()
        word_count = len(words)

        # Palabras clave de tranquilidad y control en español
        control_keywords = {"seguridad", "control", "investigando", "tranquilidad", "protocolo", "medidas", "prioridad"}
        found_keywords = [w for w in words if w in control_keywords]

        base_score = min(85, max(45, 50 + len(found_keywords) * 8))
        bridging = any(phrase in transcript.lower() for phrase in ["lo importante es", "el punto central", "nuestra prioridad"])

        return {
            "key_message_adherence_score": base_score,
            "crisis_control_score": min(100, base_score + 5),
            "bridging_detected": bridging,
            "strengths": [
                "Mantuvo una articulación verbal continua",
                "Utilizó términos de contención y control institucional" if found_keywords else "Completó la declaración formal",
            ],
            "weaknesses": [
                "Podría reforzar la reiteración de compromisos y plazos concretos",
            ] + ([f"Nota: evaluación estimada localmente ({error})"] if error else []),
            "executive_summary": "El vocero ofreció un mensaje estructurado. Se recomienda mayor énfasis en datos verificables.",
        }
