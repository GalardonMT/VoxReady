import os
import re
import json
import time
import logging
from typing import Optional, List, Dict, Any
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from openai import OpenAI
try:
    from core.schemas import EvaluacionLLMResponse, ReporteJuezConsolidado
except (ImportError, ValueError):
    from worker.core.schemas import EvaluacionLLMResponse, ReporteJuezConsolidado
logger = logging.getLogger(__name__)


def _clean_and_parse_json(content: str) -> dict:
    if not content or not content.strip():
        raise ValueError("El contenido devuelto por el LLM está vacío.")

    text = content.strip()
    # 1. Quitar markdown fences si existen
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        text = match.group(1).strip()

    # 2. Intento directo
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 3. Intentar raw_decode desde el primer '{' para ignorar 'Extra data'
    start_idx = text.find("{")
    if start_idx != -1:
        try:
            decoder = json.JSONDecoder()
            parsed, _ = decoder.raw_decode(text[start_idx:])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 4. Extraer el bloque delimitado por las llaves exteriores si hay texto adyacente
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            parsed = json.loads(text[start_idx : end_idx + 1].strip())
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return json.loads(text)


SYSTEM_PROMPT = """
Eres un consultor senior y auditor jefe de Media Training y Manejo de Crisis corporativas (Metodología VISUM), riguroso, imparcial y pedagógico.
Tu tarea es auditar la transcripción de la intervención de un vocero frente a una entrevista periodística (de turno único o multi-turno con contrapreguntas en vivo).

ESCALA CONDUCTUAL ESTÁNDAR (ENTEROS DE 1 A 5):
- Nivel 1 (Deficiente): Conducta contraproducente que anula la efectividad de la vocería, evade abiertamente o abre un riesgo reputacional/legal severo.
- Nivel 2 (Bajo): Brechas frecuentes y notorias, evasión parcial con frases vacías, vaguedad reiterada o pérdida de control ante presión.
- Nivel 3 (Adecuado): Cumple funcionalmente el estándar mínimo (delimita y comunica lo esencial), pero con oportunidades claras en agilidad, síntesis o naturalidad.
- Nivel 4 (Sólido): Desempeño consistente, claro y estratégico incluso bajo presión o contrapreguntas incisivas.
- Nivel 5 (Sobresaliente): Dominio ejemplar; responde/delimita con precisión quirúrgica, conduce la agenda con naturalidad y sostiene total coherencia y empatía.

CRITERIOS OBLIGATORIOS POR DIMENSIÓN (7 DIMENSIONES ESTRATÉGICAS):
1. pertinencia_respuesta (Peso 25% — FILTRO ANTI-EVASIÓN):
   - Evalúa si el vocero responde al núcleo de cada pregunta O delimita con fundamento válido (ej. investigación/peritaje en curso, alcance regulatorio) ANTES de transicionar a su mensaje clave.
   - Frases protocolares vacías ("entiendo la situación", "comprendo su punto", "gracias por la pregunta") NO constituyen respuesta ni delimitación.
   - Si el vocero ignora la pregunta y salta a recitar mensajes clave -> Nivel 1. Si usa solo cortesía vacía y desvía -> Nivel 2. Está PROHIBIDO asignar Nivel 3, 4 o 5 si predomina la evasión. El control legítimo del mensaje nunca es evasión.
   - REGLA MULTI-TURNO: Si el vocero evadió inicialmente una pregunta base pero RECTIFICÓ y respondió/delimitó con solvencia ante la contrapregunta inmediata, califica como máximo con Nivel 3. Si reincidió en evasión ante la contrapregunta -> Nivel 1 o 2. Si respondió/delimitó desde el primer turno y sostuvo el rigor en contrapreguntas -> Nivel 4 o 5.
2. alineacion_mensaje_clave (Peso 25%):
   - Nivel 5: Posiciona todos los mensajes clave obligatorios de forma orgánica y adaptada a las preguntas.
   - Nivel 4: Posiciona la mayoría de los mensajes clave (o todos con leve rigidez) manteniendo relevancia.
   - Nivel 3: Posiciona parcialmente los mensajes clave (al menos la idea central), omitiendo secundarios.
   - Nivel 2: Mención tangencial, incompleta o desconectada de los mensajes clave.
   - Nivel 1: Omite por completo los mensajes clave del escenario o los contradice.
   - Registra exactamente qué mensajes de la lista oficial fueron cubiertos en 'mensajes_cumplidos' y cuáles faltaron en 'mensajes_omitidos'.
3. tecnicas_control (Peso 15%):
   - Identifica el uso deliberado y pertinente de:
     * "bridging": transición legítima tras responder/delimitar ("lo concreto hasta ahora es...", "precisamente por eso la medida inmediata es...").
     * "flagging": énfasis jerárquico ("el punto central que debe quedar claro es...").
     * "hooking": apertura estratégica de datos o acciones que orienta el interés periodístico.
   - IMPORTANTE: Usar frases puente para EVADIR sin haber delimitado la pregunta es mal uso de la técnica y no puede superar Nivel 2. Nivel 4–5 exige transiciones fluidas luego de responder/delimitar. Lista las técnicas válidas observadas en 'tecnicas_detectadas' (valores permitidos: "bridging", "flagging", "hooking") y cita la mejor en 'frase_transicion' (o null si no hubo).
4. consistencia_institucional (Peso 15%):
   - Evalúa disciplina fáctica: no especular sobre causas no confirmadas, no inventar cifras fuera del contexto, no culpar a terceros sin pruebas y no asumir compromisos legales temerarios.
   - Si "infraccion_linea_roja" es true, DEBES asignar obligatoriamente Nivel 1 (0 pts) en esta dimensión.
5. asertividad_hostilidad (Peso 10%):
   - Evalúa aplomo verbal ante preguntas tensas o contrapreguntas incisivas: firmeza serena y respetuosa (Nivel 4–5) vs. tono defensivo, sarcástico, confrontacional con el periodista o dubitativo/sumiso (Nivel 1–2).
6. capacidad_sintesis (Peso 5%):
   - Evalúa economía verbal y foco: ideas estructuradas y directas al titular (Nivel 4–5) vs. rodeos extensos, redundancia circular o respuestas telegráficas insuficientes (Nivel 1–2).
7. claridad_mensaje (Peso 5%):
   - Evalúa comprensión para la audiencia objetivo: lenguaje llano y traducción pedagógica de tecnicismos (Nivel 4–5) vs. jerga críptica, sintaxis confusa o ambigüedad (Nivel 1–2).
   - NOTA SOBRE ASR: El texto proviene de reconocimiento automático de voz (ASR). No penalices errores fonéticos menores, puntuación automática imperfecta o homófonos propios del transcriptor si la estructura oral de la idea del vocero es clara.

REGLAS TRANSVERSALES ADICIONALES:
A. CERO PSICOLOGIZACIÓN: Prohibido inferir estados mentales o emocionales internos ("estaba asustado", "sintió culpa", "quiso ocultar"). Describe únicamente conductas discursivas observables y citas textuales.
B. AUDITORÍA ESTRICTA DE LÍNEAS ROJAS:
   - "infraccion_linea_roja": true SOLO si el vocero confirma, admite, valida, promete o especula explícitamente sobre lo prohibido por una línea roja del escenario.
   - Si el periodista menciona el tema de la línea roja y el vocero lo NIEGA o DELIMITA correctamente sin cruzarla, eso NO es infracción ("infraccion_linea_roja": false, "evidencia_linea_roja": null).
   - Cuando sea true, incluye en "evidencia_linea_roja" tanto la línea roja vulnerada como la cita textual exacta del vocero (indicando el número de turno si aplica).
C. RECONOCIMIENTO DE AFECTADOS / STAKEHOLDERS (EMPATÍA VERBAL, ESCALA 1–5):
   - Si el escenario involucra personas, víctimas, trabajadores, pacientes, usuarios o comunidad perjudicada:
     * Nivel 5: Prioriza desde el inicio el impacto humano/usuarios con empatía genuina antes de explicaciones técnicas o descargos corporativos.
     * Nivel 4: Reconoce con claridad y respeto a los afectados antes o junto al plan de acción.
     * Nivel 3: Mención secundaria, tardía o meramente protocolar, priorizando lo operativo.
     * Nivel 2: Mención impersonal, fría o minimizadora del impacto en las personas.
     * Nivel 1: Omisión total de los afectados centrándose solo en defensa corporativa, procesos internos o balances económicos.
   - Si el escenario es puramente técnico, regulatorio o financiero sin víctimas humanas directas: evalúa en la misma escala 1–5 cómo reconoce y atiende las preocupaciones legítimas de la audiencia/stakeholders afectados según la óptica del escenario.

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


def resolve_turn_followup_reason(
    turn: Dict[str, Any],
    all_turns: List[Dict[str, Any]],
) -> Optional[str]:
    """Resuelve el motivo editorial (triggerReason) de una contrapregunta, ya sea en el propio turno o en su turno base padre."""
    kind = str(turn.get("turnKind") or turn.get("turn_kind") or "base")
    if kind != "follow_up":
        return None

    direct = turn.get("triggerReason") or turn.get("followup_trigger_reason")
    if direct and str(direct).strip():
        return str(direct).strip()

    parent_id = str(turn.get("parentTurnId") or turn.get("parent_turn_id") or "").strip()
    base_seq = turn.get("baseSequenceNo") if turn.get("baseSequenceNo") is not None else turn.get("base_sequence_no")

    for candidate in all_turns:
        c_kind = str(candidate.get("turnKind") or candidate.get("turn_kind") or "base")
        if c_kind != "base":
            continue
        c_id = str(candidate.get("turnId") or candidate.get("turn_id") or "").strip()
        c_base_seq = (
            candidate.get("baseSequenceNo")
            if candidate.get("baseSequenceNo") is not None
            else candidate.get("base_sequence_no")
        )
        if (parent_id and c_id and c_id == parent_id) or (
            not parent_id and base_seq is not None and c_base_seq == base_seq
        ):
            reason = candidate.get("triggerReason") or candidate.get("followup_trigger_reason")
            if reason and str(reason).strip():
                return str(reason).strip()
    return None


def format_interview_dialogue(interview_turns: List[Dict[str, Any]]) -> str:
    """Formatea los turnos estructurados (base y contrapregunta con su triggerReason) para el Juez LLM y VISUM."""
    ordered = sorted(
        interview_turns,
        key=lambda t: int(t.get("turnIndex") or t.get("turn_index") or 0),
    )
    blocks: List[str] = []
    for idx, turn in enumerate(ordered, start=1):
        t_idx = int(turn.get("turnIndex") or turn.get("turn_index") or idx)
        base_seq = int(turn.get("baseSequenceNo") or turn.get("base_sequence_no") or idx)
        kind = str(turn.get("turnKind") or turn.get("turn_kind") or "base")
        q_text = str(turn.get("questionText") or turn.get("question_text") or "").strip()
        ans_text = str(turn.get("transcript") or "").strip() or "(Sin respuesta inteligible)"
        if kind == "follow_up":
            reason = resolve_turn_followup_reason(turn, ordered)
            reason_suffix = f" · Motivo detectado en vivo: {reason}" if reason else ""
            header = f"[Turno {t_idx} · Contrapregunta IA sobre Pregunta Base #{base_seq}{reason_suffix}]"
        else:
            header = f"[Turno {t_idx} · Pregunta Base #{base_seq}]"
        blocks.append(f"{header}\nPeriodista: \"{q_text}\"\nVocero: \"{ans_text}\"")
    return "\n\n".join(blocks)


class LLMJudgeService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fast_model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        try:
            from services.keyvault_service import get_secret
            kv_get = get_secret
        except ImportError:
            kv_get = lambda k, d=None: os.getenv(k, d)

        # 1. Resolver API Key (Prioridad: Gemini -> Key Vault -> NVIDIA fallback)
        self.api_key = (
            api_key
            or kv_get("GEMINI_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or kv_get("gemini-api-key")
            or kv_get("NVIDIA_API_KEY")
            or os.getenv("NVIDIA_API_KEY")
        )

        is_gemini = bool(self.api_key and not self.api_key.startswith("nvapi-"))

        # 2. Resolver Base URL asegurando la regla crítica de terminar con '/'
        if is_gemini:
            default_base = "https://generativelanguage.googleapis.com/v1beta/openai/"
            default_primary = "gemini-3.5-flash-lite"
            default_fast = "gemini-3.5-flash-lite"
        else:
            default_base = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            default_primary = os.getenv("LLM_MODEL_NAME", "deepseek-ai/deepseek-v4.1-flash")
            default_fast = "deepseek-ai/deepseek-v4.1-flash"

        raw_base_url = (
            base_url
            or kv_get("GEMINI_OPENAI_BASE_URL")
            or os.getenv("GEMINI_OPENAI_BASE_URL")
            or default_base
        ).strip()
        if "generativelanguage.googleapis.com" in raw_base_url and not raw_base_url.endswith("/"):
            raw_base_url += "/"
        elif not raw_base_url.endswith("/chat/completions") and not raw_base_url.endswith("/"):
            raw_base_url = raw_base_url.rstrip("/")
        if raw_base_url.endswith("/chat/completions"):
            raw_base_url = raw_base_url[:-len("/chat/completions")].rstrip("/")
        self.base_url = raw_base_url

        # 3. Modelos primario y de respaldo rápido
        self.model = (
            model
            or kv_get("GEMINI_JUDGE_MODEL")
            or os.getenv("GEMINI_JUDGE_MODEL")
            or default_primary
        )
        self.fast_model = (
            fast_model
            or kv_get("GEMINI_FAST_MODEL")
            or os.getenv("GEMINI_FAST_MODEL")
            or default_fast
        )

        # 4. Timeout (30s por defecto para balancear inferencia y latencia)
        self.timeout = timeout if timeout is not None else float(
            kv_get("LLM_TIMEOUT", "30.0") or os.getenv("LLM_TIMEOUT", "30.0")
        )

        if not self.api_key:
            logger.warning("Ni GEMINI_API_KEY ni NVIDIA_API_KEY están configuradas en variables de entorno o Key Vault.")

        self._client = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            import httpx
            http_client = httpx.Client(verify=False, timeout=self.timeout)
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=0,
                http_client=http_client,
            )
        return self._client


    def evaluate_response(
        self,
        pregunta_periodista: str,
        mensajes_clave: List[str],
        contexto_crisis: str,
        transcripcion_vocero: str,
        lineas_rojas: Optional[List[str]] = None,
        interview_turns: Optional[List[Dict[str, Any]]] = None,
        scenario_title: Optional[str] = None,
        optica: Optional[str] = None,
        audiencia: Optional[str] = None,
        dificultad: Optional[str] = None,
    ) -> ReporteJuezConsolidado:

        lineas_rojas_list = lineas_rojas or []
        if lineas_rojas_list:
            lineas_rojas_text = "\n".join(f"- \"{rl}\"" for rl in lineas_rojas_list)
        else:
            lineas_rojas_text = "- (No hay líneas rojas definidas para este escenario)"

        titulo_escenario = (scenario_title or "Simulación de Vocería en Crisis").strip()
        optica_escenario = (optica or "institucional, empática y rigurosa").strip()
        audiencia_escenario = (audiencia or "opinión pública y medios de comunicación").strip()
        dificultad_escenario = (dificultad or "intermediate").strip()

        if interview_turns:
            dialogue_block = format_interview_dialogue(interview_turns)
            interaction_section = f"""DIÁLOGO COMPLETO DE LA ENTREVISTA POR TURNOS (PREGUNTAS BASE Y CONTRAPREGUNTAS EN VIVO):
{dialogue_block}

GUÍA DE AUDITORÍA MULTI-TURNO:
Evalúa el desempeño global ponderando cada par pregunta-respuesta y la evolución del vocero bajo contrapregunta: verifica si el motivo detectado en vivo se confirma en la transcripción y si en la contrapregunta el vocero logró corregir el flanco (máximo Nivel 3 en pertinencia si hubo evasión inicial), reincidió en evasión (Nivel 1–2), sostuvo sus mensajes clave o cedió hacia una línea roja."""
        else:
            interaction_section = f"""PREGUNTA FORMULADA POR EL PERIODISTA:
"{pregunta_periodista}"

TRANSCRIPCIÓN DE LA RESPUESTA REAL DEL VOCERO:
"{transcripcion_vocero}" """

        user_prompt = f"""ESCENARIO: {titulo_escenario}
ÓPTICA INSTITUCIONAL: {optica_escenario} | AUDIENCIA OBJETIVO: {audiencia_escenario} | DIFICULTAD: {dificultad_escenario}
CONTEXTO DEL ESCENARIO:
{contexto_crisis}

MENSAJES CLAVE OBLIGATORIOS QUE EL VOCERO DEBÍA POSICIONAR:
{json.dumps(mensajes_clave, ensure_ascii=False, indent=2)}

LÍNEAS ROJAS DEL ESCENARIO (ESTRICTAMENTE PROHIBIDAS PARA EL VOCERO):
{lineas_rojas_text}

{interaction_section}

INSTRUCCIONES DE SALIDA JSON ESTRICTA:
Devuelve un único objeto JSON con estas claves exactas:
1. "evaluacion_dimensiones": objeto con las 7 claves obligatorias:
   - "pertinencia_respuesta": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "..."}}
   - "tecnicas_control": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "...", "tecnicas_detectadas": ["bridging"|"flagging"|"hooking"], "frase_transicion": "..." o null}}
   - "alineacion_mensaje_clave": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "...", "mensajes_cumplidos": ["..."], "mensajes_omitidos": ["..."]}}
   - "capacidad_sintesis": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "..."}}
   - "claridad_mensaje": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "..."}}
   - "consistencia_institucional": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "..."}}
   - "asertividad_hostilidad": {{"nivel": 1..5, "criterio": "...", "evidencia_textual": "..."}}
   (En todas las citas de 'evidencia_textual', usa frases literales del vocero indicando "[Turno N]" cuando haya múltiples turnos, o "" si hubo omisión total).
2. "feedback_pedagogico": {{
     "fortaleza_principal": "<principal competencia demostrada con sustento en el diálogo (si no hay fortalezas consolidadas, describir objetivamente la ausencia de fortalezas en vez de null)>",
     "brecha_critica": "<principal vulnerabilidad estratégica observada y su riesgo comunicacional>",
     "recomendacion_accionable": "<acción concreta y entrenable para corregir la brecha crítica en la próxima vocería>"
   }}
3. "infraccion_linea_roja": true o false (booleano primitivo true o false, NUNCA un objeto o diccionario). Si es true, verifica que "consistencia_institucional.nivel" sea 1.
4. "evidencia_linea_roja": string citando la línea roja vulnerada y la frase exacta del vocero, o null si "infraccion_linea_roja" es false.
5. "reconocimiento_afectados": {{"nivel": 1..5, "criterio": "<justificación breve>", "evidencia_textual": "<cita literal o texto vacío>"}}
"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        parsed_eval: Optional[EvaluacionLLMResponse] = None
        models_to_try = [
            (self.model, "medium"),
            (self.fast_model, "low"),
        ]

        logger.info(
            f"[LLMJudge] Evaluando respuesta vocero con {self.model} (respaldo: {self.fast_model}, endpoint: {self.base_url}, timeout: {self.timeout}s)..."
        )

        last_error: Optional[Exception] = None

        for target_model, effort in models_to_try:
            for attempt in range(1, 3):
                logger.info(f"[LLMJudge] Intentando {target_model} (intento {attempt}/2)...")
                try:
                    # 1. Intentar Structured Outputs vía beta.chat.completions.parse
                    completion = self.client.beta.chat.completions.parse(
                        model=target_model,
                        messages=messages,
                        temperature=0.2,
                        response_format=EvaluacionLLMResponse,
                        extra_body={"reasoning_effort": effort},
                        timeout=self.timeout,
                    )
                    parsed_eval = completion.choices[0].message.parsed
                    if parsed_eval:
                        break
                except Exception as parse_err:
                    last_error = parse_err
                    # Comprobar si el error es transitorio de servicio (429 RateLimit o 503 High Demand)
                    status_code = getattr(parse_err, "status_code", None)
                    if hasattr(parse_err, "response") and getattr(parse_err.response, "status_code", None):
                        status_code = parse_err.response.status_code

                    is_transient = (
                        status_code in [429, 502, 503, 504]
                        or "high demand" in str(parse_err).lower()
                        or "503" in str(parse_err)
                        or "504" in str(parse_err)
                        or "timeout" in str(parse_err).lower()
                    )

                    if is_transient:
                        if attempt == 1:
                            logger.warning(
                                f"[LLMJudge] Error transitorio con {target_model} (código {status_code}): {parse_err}. Reintentando en 2s para liberar cuota de ráfaga..."
                            )
                            time.sleep(2.0)
                            continue
                        else:
                            logger.warning(
                                f"[LLMJudge] Persiste error transitorio con {target_model} tras reintento. Cambiando de modelo..."
                            )
                            break

                    # Si el error no es transitorio o falló parse, intentar fallback con json_object estándar
                    try:
                        raw_resp = self.client.chat.completions.create(
                            model=target_model,
                            messages=messages,
                            temperature=0.2,
                            max_tokens=3072,
                            timeout=self.timeout,
                            response_format={"type": "json_object"},
                            extra_body={"reasoning_effort": effort},
                        )
                        raw_content = raw_resp.choices[0].message.content or ""
                        if raw_content.strip():
                            raw_json = _clean_and_parse_json(raw_content)
                            parsed_eval = EvaluacionLLMResponse.model_validate(raw_json)
                            break
                    except Exception as json_err:
                        last_error = json_err
                        logger.warning(f"[LLMJudge] Falló intento con {target_model}: {json_err}")
                        break

            if parsed_eval is not None:
                break
            logger.warning(f"[LLMJudge] Cambiando a modelo alternativo tras fallo con {target_model}...")

        if parsed_eval is None:
            err_detail = ""
            if hasattr(last_error, "response") and getattr(last_error.response, "text", None):
                err_detail = f" - Detalle API: {last_error.response.text}"
            logger.error(f"[LLMJudge] Fallo crítico evaluando respuesta tras reintentos: {last_error}{err_detail}")
            raise RuntimeError(f"Error evaluando el contenido con LLM Juez: {last_error}{err_detail}") from last_error

        # Si hubo infracción de línea roja, asegurar Nivel 1 en consistencia_institucional
        if parsed_eval.infraccion_linea_roja:
            parsed_eval.evaluacion_dimensiones.consistencia_institucional.nivel = 1
            if not parsed_eval.evaluacion_dimensiones.consistencia_institucional.criterio:
                parsed_eval.evaluacion_dimensiones.consistencia_institucional.criterio = (
                    f"Transgresión de línea roja institucional: {parsed_eval.evidencia_linea_roja or 'Infracción crítica'}"
                )

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

            entry: Dict[str, Any] = {
                "nivel": nivel,
                "nivel_visum": nivel,
                "score_100": round(score_dim_100, 2),
                "peso_ponderado": peso,
                "criterio": dim_data.get("criterio"),
                "evidencia": dim_data.get("evidencia_textual"),
            }
            if dim == "tecnicas_control":
                entry["tecnicas_detectadas"] = list(dim_data.get("tecnicas_detectadas") or [])
                entry["frase_transicion"] = dim_data.get("frase_transicion")
            elif dim == "alineacion_mensaje_clave":
                entry["mensajes_cumplidos"] = list(dim_data.get("mensajes_cumplidos") or [])
                entry["mensajes_omitidos"] = list(dim_data.get("mensajes_omitidos") or [])

            dimensiones_normalizadas[dim] = entry

        # Procesar reconocimiento de afectados
        rec_obj = parsed_eval.reconocimiento_afectados
        if rec_obj:
            rec_dict = {
                "nivel": rec_obj.nivel,
                "score_100": round(((rec_obj.nivel - 1) / 4.0) * 100.0, 1),
                "criterio": rec_obj.criterio,
                "evidencia": rec_obj.evidencia_textual or "",
            }
        else:
            rec_dict = {
                "nivel": 3,
                "score_100": 50.0,
                "criterio": "Mención neutra de afectados.",
                "evidencia": "",
            }

        return ReporteJuezConsolidado(
            puntaje_global_100=round(puntaje_global_100, 2),
            dimensiones=dimensiones_normalizadas,
            feedback=parsed_eval.feedback_pedagogico,
            raw_evaluation=parsed_eval,
            infraccion_linea_roja=parsed_eval.infraccion_linea_roja,
            evidencia_linea_roja=parsed_eval.evidencia_linea_roja,
            reconocimiento_afectados=rec_dict,
        )


class LLMJudge(LLMJudgeService):
    """
    Wrapper compatible hacia atrás para llamadas previas tipo evaluate_transcript.
    """

    def evaluate_transcript(
        self,
        transcript: str,
        crisis_context: Optional[str] = None,
        key_messages: Optional[List[str]] = None,
        question: Optional[str] = None,
        red_lines: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not transcript or not transcript.strip():
            return {
                "puntaje_global_100": 0.0,
                "key_message_adherence_score": 0,
                "crisis_control_score": 0,
                "bridging_detected": False,
                "infraccion_linea_roja": False,
                "evidencia_linea_roja": None,
                "reconocimiento_afectados": {"nivel": 1, "score_100": 0.0, "criterio": "Sin transcripción."},
                "strengths": [],
                "weaknesses": ["No se detectó audio ni transcripción inteligible."],
                "executive_summary": "No fue posible evaluar la declaración debido a la ausencia de contenido verbal.",
            }

        try:
            reporte = self.evaluate_response(
                pregunta_periodista=question or "¿Cuál es la postura oficial y qué medidas urgentes se están adoptando?",
                mensajes_clave=key_messages or ["Nuestra máxima prioridad es la seguridad y el restablecimiento del servicio."],
                contexto_crisis=crisis_context or "Incidente corporativo y vocería de crisis.",
                transcripcion_vocero=transcript,
                lineas_rojas=red_lines,
            )
            reporte_dict = reporte.model_dump()
            # Mapear claves heredadas para compatibilidad con dashboards frontend existentes
            reporte_dict["key_message_adherence_score"] = int(
                reporte.dimensiones.get("alineacion_mensaje_clave", {}).get("score_100", 75)
            )
            reporte_dict["crisis_control_score"] = int(
                reporte.dimensiones.get("tecnicas_control", {}).get("score_100", 75)
            )
            tecnicas_det = reporte.dimensiones.get("tecnicas_control", {}).get("tecnicas_detectadas", [])
            frase_trans = reporte.dimensiones.get("tecnicas_control", {}).get("frase_transicion")
            reporte_dict["bridging_detected"] = (
                any("bridg" in str(t).lower() for t in tecnicas_det) or bool(frase_trans)
            )
            reporte_dict["infraccion_linea_roja"] = reporte.infraccion_linea_roja
            reporte_dict["evidencia_linea_roja"] = reporte.evidencia_linea_roja
            reporte_dict["reconocimiento_afectados"] = reporte.reconocimiento_afectados
            reporte_dict["strengths"] = [reporte.feedback.fortaleza_principal] if reporte.feedback.fortaleza_principal else []
            reporte_dict["weaknesses"] = [reporte.feedback.brecha_critica] if reporte.feedback.brecha_critica else []
            reporte_dict["executive_summary"] = reporte.feedback.recomendacion_accionable
            return reporte_dict
        except Exception as e:
            logger.error(f"Evaluación LLM Juez falló: {e}")
            raise RuntimeError(f"Error evaluando el contenido con el Juez LLM: {e}") from e

