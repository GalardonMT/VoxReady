import os
import re
import json
import logging
from typing import Optional, List
from dotenv import load_dotenv
from openai import OpenAI
from core.schemas import EvaluacionLLMResponse, ReporteJuezConsolidado

load_dotenv()
logger = logging.getLogger(__name__)


def _clean_and_parse_json(content: str) -> dict:
    text = content.strip()
    # 1. Quitar markdown fences si existen
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    # 2. Extraer el bloque delimitado por las llaves exteriores si hay texto adyacente
    if not text.startswith("{"):
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1].strip()

    return json.loads(text)

SYSTEM_PROMPT = """
Eres un consultor senior de Media Training y Manejo de Crisis corporativas, riguroso, crítico y pedagógico.
Tu tarea es auditar la respuesta transcrita de un vocero frente a una pregunta periodística o de confrontación pública.

Debes evaluar 7 variables específicas utilizando exclusivamente los 5 niveles de desempeño de la escala estándar:
- Nivel 1 (Deficiente): La conducta afecta significativamente la efectividad de la vocería o genera un riesgo comunicacional/legal.
- Nivel 2 (Bajo): Existen brechas frecuentes y perceptibles que dificultan el desempeño o denotan evasión evidente.
- Nivel 3 (Adecuado): Cumple funcionalmente el estándar, aunque presenta oportunidades claras de mejora en naturalidad o agilidad.
- Nivel 4 (Sólido): Desempeño consistente, efectivo y adecuado incluso ante preguntas hostiles.
- Nivel 5 (Sobresaliente): Dominio consistente, adaptación estratégica impecable y alta capacidad de persuasión.

REGLAS DE EVALUACIÓN OBLIGATORIAS:
1. FILTRO ANTI-EVASIÓN (PERTINENCIA ANTES DE BRIDGING):
   Evalúa si el vocero responde o delimita el núcleo de la pregunta antes de transicionar al mensaje estratégico.
   Frases protocolares como "entiendo la situación" o "comprendo su punto" NO constituyen respuesta ni delimitación.
   Si el vocero introduce una frase puente (bridging) para recitar su mensaje clave sin haber delimitado o respondido la pregunta específica formulada, la dimensión 'pertinencia_respuesta' DEBE ser calificada obligatoriamente con Nivel 1 (si ignora totalmente) o Nivel 2 (si evade usando solo una frase vacía de cortesía). Está PROHIBIDO calificar con Nivel 3, 4 o 5 cuando hay evasión. El control del mensaje nunca es evasión.
2. TÉCNICAS DE CONTROL: Identifica si existen frases deliberadas de:
   - Bridging: puente hacia el mensaje ('lo crucial aquí es', 'el hecho concreto es').
   - Flagging: marcar lo central ('el punto principal que debe quedar claro').
   - Hooking: dejar un anzuelo temático para guiar la siguiente pregunta.
3. CERO PSICOLOGIZACIÓN: No asumas ni intentes adivinar emociones internas ('estaba asustado', 'sintió culpa'). Limítate estrictamente a lo que las palabras observables reflejan.
4. CONSISTENCIA INSTITUCIONAL: Penaliza severamente cualquier especulación sobre cifras, causas no confirmadas o promesas que comprometan legalmente a la organización.

Responde ÚNICAMENTE con un objeto JSON válido según la estructura requerida.
"""

PESOS_DIMENSIONES = {
    "pertinencia_respuesta": 0.25,
    "alineacion_mensaje_clave": 0.25,
    "tecnicas_control": 0.15,
    "consistencia_institucional": 0.15,
    "asertividad_hostilidad": 0.10,
    "capacidad_sintesis": 0.05,
    "claridad_mensaje": 0.05,
}

class LLMJudgeService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        
        # Sanitizar base_url: OpenAI SDK concatena /chat/completions por defecto.
        # Si el usuario colocó '/chat/completions' al final, se normaliza automáticamente.
        raw_base_url = (
            base_url
            or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        ).strip().rstrip("/")
        if raw_base_url.endswith("/chat/completions"):
            raw_base_url = raw_base_url[:-len("/chat/completions")].rstrip("/")
        self.base_url = raw_base_url

        self.model = model or os.getenv(
            "LLM_MODEL_NAME", "meta/llama-3.2-11b-vision-instruct"
        )
        
        # Timeout amplio (120s por defecto) para permitir que NVIDIA NIM termine la inferencia
        self.timeout = timeout if timeout is not None else float(
            os.getenv("LLM_TIMEOUT", "120.0")
        )

        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY no configurada en las variables de entorno")

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def evaluate_response(
        self,
        pregunta_periodista: str,
        mensajes_clave: List[str],
        contexto_crisis: str,
        transcripcion_vocero: str,
    ) -> ReporteJuezConsolidado:

        user_prompt = f"""
CONTEXTO DEL ESCENARIO:
{contexto_crisis}

PREGUNTA FORMULADA POR EL PERIODISTA:
"{pregunta_periodista}"

MENSAJES CLAVE OBLIGATORIOS QUE EL VOCERO DEBÍA TRANSMITIR:
{json.dumps(mensajes_clave, ensure_ascii=False, indent=2)}

TRANSCRIPCIÓN DE LA RESPUESTA REAL DEL VOCERO:
"{transcripcion_vocero}"

REGLA CRÍTICA PARA 'pertinencia_respuesta':
- Si el vocero NO responde ni delimita la pregunta concreta (ej: ignora la consulta sobre alertas o hechos imputados y salta directo a recitar mensajes clave con bridging), asigna obligatoriamente NIVEL 1 o 2.
- Si el vocero delimita o responde la pregunta antes de tender el puente al mensaje clave, califica según la solidez demostrada (Nivel 3, 4 o 5).

Genera el análisis en formato JSON estricto con las claves:
- evaluacion_dimensiones (pertinencia_respuesta, tecnicas_control, alineacion_mensaje_clave, capacidad_sintesis, claridad_mensaje, consistencia_institucional, asertividad_hostilidad)
  Cada dimensión debe contener: 'nivel' (entero 1 a 5), 'criterio' (justificación cualitativa), 'evidencia_textual' (cita exacta).
- feedback_pedagogico (fortaleza_principal, brecha_critica, recomendacion_accionable)
"""
        print(user_prompt)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
                timeout=self.timeout,
                response_format={"type": "json_object"},
            )
        except Exception as primary_err:
            # Si el modelo primario falla o da timeout y no es el 11B ligero, reintentar con 11B
            fallback_model = "meta/llama-3.2-11b-vision-instruct"
            if self.model != fallback_model:
                logger.warning(
                    f"Fallo con {self.model} ({primary_err}). Reintentando con modelo ligero {fallback_model}..."
                )
                print(f"[REINTENTO] Fallo con {self.model} ({primary_err}). Reintentando con {fallback_model}...")
                response = self.client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                    timeout=self.timeout,
                    response_format={"type": "json_object"},
                )
            else:
                raise primary_err

        content = response.choices[0].message.content
        raw_json = _clean_and_parse_json(content)
        parsed_eval = EvaluacionLLMResponse.model_validate(raw_json)

        # Cálculo matemático determinista (escala 0 a 100)
        dimensiones_dict = parsed_eval.evaluacion_dimensiones.model_dump()
        puntaje_global_100 = 0.0
        dimensiones_normalizadas = {}

        for dim, peso in PESOS_DIMENSIONES.items():
            dim_data = dimensiones_dict.get(dim, {})
            nivel = dim_data.get("nivel", 1)
            # Normalización lineal: Nivel 1 = 0 pts, Nivel 5 = 100 pts
            score_dim_100 = ((nivel - 1) / 4.0) * 100.0
            puntaje_global_100 += score_dim_100 * peso

            dimensiones_normalizadas[dim] = {
                "nivel_visum": nivel,
                "score_100": round(score_dim_100, 2),
                "peso_ponderado": peso,
                "criterio": dim_data.get("criterio"),
                "evidencia": dim_data.get("evidencia_textual"),
            }

        return ReporteJuezConsolidado(
            puntaje_global_100=round(puntaje_global_100, 2),
            dimensiones=dimensiones_normalizadas,
            feedback=parsed_eval.feedback_pedagogico,
            raw_evaluation=parsed_eval,
        )
