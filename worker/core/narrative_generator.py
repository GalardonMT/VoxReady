import os
import re
import json
import time
import logging
from typing import Dict, Any, List, Optional
from openai import OpenAI

try:
    from core.schemas import InformeVisumResponse
    from core.llm_judge import resolve_turn_followup_reason
except (ImportError, ValueError):
    from worker.core.schemas import InformeVisumResponse
    from worker.core.llm_judge import resolve_turn_followup_reason

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VISUM = """Eres un consultor senior de comunicaciones estratégicas y media training de VISUM Consulting.
Tu tarea es redactar el Informe Ejecutivo de Evaluación de Vocería a partir de las métricas multimodales consolidadas y del dictamen estructurado del Juez de Contenido.

PRINCIPIOS DE CONSISTENCIA Y FIDELIDAD ESTRICTA (REGLAS INQUEBRANTABLES):
1. FIDELIDAD ABSOLUTA A LOS DATOS Y AL DICTAMEN DEL JUEZ:
   - Tus conclusiones narrativas DEBEN ser 100% coherentes con `metricas_consolidadas`, `bandas_rubrica` ("optimal", "warning", "critical") y `dictamen_juez_contenido`.
   - Está PROHIBIDO elogiar como fortaleza una dimensión calificada con Nivel 1 o 2 por el Juez o una métrica clasificada en banda "critical".
   - Está PROHIBIDO señalar como deficiente una métrica clasificada en banda "optimal" o con Nivel 4–5, salvo para sugerir perfeccionamiento avanzado.
   - Si `dictamen_juez_contenido.infraccion_linea_roja` es `true`, DEBES abordar explícitamente dicha vulneración (citando `evidencia_linea_roja`) en `diagnostico_general`, en el primer ítem de `oportunidades_desarrollo` y en `hallazgos_transversales` bajo la prioridad `"Delimitación institucional"`.
2. CALIBRACIÓN DEL TONO EJECUTIVO SEGÚN TRAMO DE DESEMPEÑO:
   Mantén siempre la filosofía VISUM ("Comunicar bien no es un talento innato: es una disciplina que se entrena"), adaptando el encuadre al resultado real indicado en `metricas_consolidadas.tramo_desempeno`:
   - TRAMO SÓLIDO / SOBRESALIENTE (`solido_sobresaliente`: `score_global >= 75` e `infraccion_linea_roja == false`): Valida el piso sólido de competencias demostrado y orienta el `foco_desarrollo` a evolucionar de responder correctamente a conducir estratégicamente la conversación.
   - TRAMO EN DESARROLLO (`en_desarrollo`: `50 <= score_global < 75` e `infraccion_linea_roja == false`): Reconoce con equilibrio los recursos iniciales presentes sin sobredimensionarlos y enfoca el desarrollo en consolidar estructura, pertinencia y consistencia bajo presión.
   - TRAMO CRÍTICO O CON LÍNEA ROJA (`critico_o_linea_roja`: `score_global < 50` O `infraccion_linea_roja == true`): Mantén un tono respetuoso, ejecutivo y constructivo, pero NO afirmes que existe un "piso sólido consolidado". Diagnostica con claridad ejecutiva los riesgos comunicacionales observados y prioriza reglas básicas de contención, delimitación y apego al mensaje antes de técnicas avanzadas.
3. TRADUCCIÓN DE MÉTRICAS TÉCNICAS A IMPACTO COMUNICACIONAL (SIN INVENTAR DATOS):
   - Contacto visual, estabilidad postural, balanceo y uso de manos -> Aplomo no verbal, compostura escénica y credibilidad ante cámara.
   - Ritmo (WPM), ratio de fonación, pausas de vacilación/prolongadas, densidad de muletillas y dicción -> Control respiratorio/emocional, claridad expositiva y peso de las ideas.
   - Dimensiones del Juez (pertinencia, mensajes cumplidos/omitidos, técnicas de control, empatía verbal y líneas rojas) -> Disciplina informativa, sensibilidad hacia los afectados y conducción de agenda.
4. REGLA ANTI-ALUCINACIÓN EN SEÑAL CRUZADA (`observacion_senal_cruzada`):
   - Apóyate estrictamente en las métricas globales y en los indicadores por turno (`evaluacion_turno`, `voz_turno` y `vision_turno` dentro de `dialogo_por_turnos` cuando estén presentes).
   - Si `dialogo_por_turnos` incluye métricas por turno, PUEDES contrastar variaciones reales entre turnos (ej. caída de contacto visual o aumento de WPM/muletillas en una contrapregunta frente al turno base).
   - NUNCA inventes microgestos en segundos o palabras específicas que no estén respaldados por los datos medidos del expediente.
5. FÓRMULAS PRÁCTICAS VISUM (ELIGE Y ADAPTA AL ESCENARIO LA MÁS PERTINENTE A LA BRECHA PRINCIPAL):
   - Crisis operacional o con afectados -> Secuencia en 3 pasos adaptada al caso: 1) Reconocer el impacto humano/operativo -> 2) Explicar certezas verificadas sin especular -> 3) Detallar acciones concretas en curso.
   - Entrevista de alta complejidad técnica/regulatoria -> Fórmula de traducción pedagógica adaptada al caso: "Para que todas las personas lo entiendan con claridad, lo esencial aquí se resume en tres hechos..."
   - Presión sobre líneas rojas o preguntas especulativas -> Fórmula de delimitación + puente (Bridging legítimo): "Ese aspecto específico está en proceso de [peritaje/verificación] y sería irresponsable adelantar conclusiones; lo que sí está confirmado hoy es [mensaje clave]".
   - Preparación estratégica previa / off the record -> Pregunta guía: "¿Qué titular verificado y qué prioridad humana debe llevarse la audiencia después de escucharme?"

ESQUEMA JSON DE RESPUESTA REQUERIDO:
Responde EXCLUSIVAMENTE con un objeto JSON válido con la siguiente estructura exacta:
{
  "sintesis_ejecutiva": {
    "diagnostico_general": "Párrafo ejecutivo de 3 a 4 oraciones alineado estrictamente con score_global, puntajes de las 4 áreas y estado de línea roja.",
    "fortaleza_principal": "Competencia mejor consolidada según los puntajes más altos de los canales evaluados (si todos los ejes son bajos, destaca el aspecto relativamente más estable sin exagerarlo).",
    "foco_desarrollo": "Prioridad central de evolución pedagógica acorde al tramo real de desempeño.",
    "continuidad_recomendada": "Recomendación concreta de práctica en simulador (nivel de dificultad y foco de entrenamiento sugerido)."
  },
  "desempeno_observado": {
    "evaluacion_general": "Análisis integrado (4 a 6 oraciones) de cómo gestionó la entrevista, incluyendo explícitamente su respuesta ante contrapreguntas si hubo múltiples turnos.",
    "fortalezas": [
      "Fortaleza concreta 1 respaldada por métrica optimal/sólida o dimensión alta del Juez",
      "Fortaleza concreta 2 respaldada por evidencia observable",
      "Fortaleza concreta 3 (o aspecto base rescatable si el desempeño global fue crítico)"
    ],
    "oportunidades_desarrollo": [
      "Oportunidad prioritaria 1 alineada con la brecha_critica del Juez o alerta de línea roja",
      "Oportunidad accionable 2 alineada con brechas verbales/prosódicas o mensajes clave omitidos",
      "Oportunidad accionable 3 alineada con expresión no verbal, empatía o conducción estratégica"
    ],
    "formula_practica_recomendada": "Guion breve de 2 a 3 líneas listo para decir en voz alta, aplicando la fórmula VISUM elegida con vocabulario propio del escenario evaluado."
  },
  "hallazgos_transversales": [
    {
      "prioridad": "Delimitación institucional | Conducción estratégica | Empatía como primera señal | Pedagogía de la complejidad",
      "descripcion": "Explicación ejecutiva del hallazgo y su impacto directo en la credibilidad ante la audiencia del escenario."
    }
  ],
  "recomendaciones_proximas_vocerias": [
    "Regla práctica y accionable 1",
    "Regla práctica y accionable 2",
    "Regla práctica y accionable 3",
    "Regla práctica y accionable 4"
  ],
  "consideracion_final": "Párrafo breve de cierre motivador y profesional alineado con la disciplina de entrenamiento VISUM.",
  "observacion_senal_cruzada": "Análisis verificable de congruencia o disonancia entre los indicadores medidos de cámara/voz y las citas reales del discurso."
}
"""


def _parse_llm_json(text: str) -> dict:
    """Extrae y parsea de forma robusta un objeto JSON devuelto por el LLM, tolerando extra data o markdown."""
    if not text or not text.strip():
        raise ValueError("El contenido devuelto por el LLM está vacío.")

    clean = text.strip()

    # 1. Si viene envuelto en markdown ```json ... ```, extraer contenido del bloque
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean, re.IGNORECASE)
    if match:
        clean = match.group(1).strip()

    # 2. Intento directo con json.loads
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 3. Intentar raw_decode desde el primer '{' para ignorar cualquier texto sobrante (Extra data)
    start_idx = clean.find("{")
    if start_idx != -1:
        try:
            decoder = json.JSONDecoder()
            parsed, _ = decoder.raw_decode(clean[start_idx:])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 4. Intentar recortar entre el primer '{' y el último '}'
    start_idx = clean.find("{")
    end_idx = clean.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            parsed = json.loads(clean[start_idx : end_idx + 1].strip())
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 5. Si todo falla, intentar json.loads estándar para propagar la excepción informativa
    return json.loads(clean)


def compute_performance_tier(score_global: float, infraccion_linea_roja: bool) -> str:
    """Clasifica deterministamente el tramo narrativo de desempeño para alinear VISUM con la rúbrica."""
    if infraccion_linea_roja or float(score_global) < 50.0:
        return "critico_o_linea_roja"
    if float(score_global) < 75.0:
        return "en_desarrollo"
    return "solido_sobresaliente"


def _summarize_judge_for_visum(judge_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compacta el dictamen del Juez LLM preservando niveles, criterios, evidencias y línea roja."""
    if not isinstance(judge_data, dict) or not judge_data:
        return {}

    raw_dims = judge_data.get("dimensiones") or judge_data.get("dimensiones_visum") or {}
    compact_dims: Dict[str, Any] = {}
    mensajes_cumplidos: List[str] = list(judge_data.get("mensajes_cumplidos") or [])
    mensajes_omitidos: List[str] = list(judge_data.get("mensajes_omitidos") or [])

    if isinstance(raw_dims, dict):
        for dim_key, dim_val in raw_dims.items():
            if not isinstance(dim_val, dict):
                continue
            nivel = dim_val.get("nivel", dim_val.get("nivel_visum", 1))
            compact_dims[dim_key] = {
                "nivel": nivel,
                "score_100": dim_val.get("score_100", dim_val.get("score", 0.0)),
                "criterio": dim_val.get("criterio") or "",
                "evidencia": dim_val.get("evidencia") or dim_val.get("evidencia_textual") or "",
            }
            if dim_key == "alineacion_mensaje_clave":
                if not mensajes_cumplidos and dim_val.get("mensajes_cumplidos"):
                    mensajes_cumplidos = list(dim_val["mensajes_cumplidos"])
                if not mensajes_omitidos and dim_val.get("mensajes_omitidos"):
                    mensajes_omitidos = list(dim_val["mensajes_omitidos"])
            elif dim_key == "tecnicas_control":
                if dim_val.get("tecnicas_detectadas") is not None:
                    compact_dims[dim_key]["tecnicas_detectadas"] = list(dim_val.get("tecnicas_detectadas") or [])
                if dim_val.get("frase_transicion"):
                    compact_dims[dim_key]["frase_transicion"] = dim_val.get("frase_transicion")

    fb_raw = judge_data.get("feedback") or judge_data.get("feedback_pedagogico") or {}
    if hasattr(fb_raw, "model_dump"):
        fb_raw = fb_raw.model_dump()
    feedback_dict = (
        {
            "fortaleza_principal": fb_raw.get("fortaleza_principal", ""),
            "brecha_critica": fb_raw.get("brecha_critica", ""),
            "recomendacion_accionable": fb_raw.get("recomendacion_accionable", ""),
        }
        if isinstance(fb_raw, dict)
        else {}
    )

    return {
        "infraccion_linea_roja": bool(judge_data.get("infraccion_linea_roja", False)),
        "evidencia_linea_roja": judge_data.get("evidencia_linea_roja"),
        "mensajes_cumplidos": mensajes_cumplidos,
        "mensajes_omitidos": mensajes_omitidos,
        "feedback_pedagogico": feedback_dict,
        "dimensiones": compact_dims,
    }


def _build_emergency_visum_fallback(
    score_global: float,
    infraccion_linea_roja: bool,
    evidencia_linea_roja: Optional[str],
    judge_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Construye una estructura VISUM determinista y fiel a la rúbrica ante fallo total de API."""
    fb = judge_summary.get("feedback_pedagogico") or {}
    fortaleza_juez = fb.get("fortaleza_principal") or "Mantenimiento de la disposición formal durante la intervención."
    brecha_juez = fb.get("brecha_critica") or "Reforzar la delimitación de preguntas y el posicionamiento de mensajes clave."
    rec_juez = fb.get("recomendacion_accionable") or "Practicar transiciones estructuradas tras delimitar cada consulta."

    if infraccion_linea_roja:
        detalle_lr = evidencia_linea_roja or "Transgresión de límite institucional del escenario"
        diagnostico = (
            f"La vocería obtuvo un puntaje global de {score_global:.1f}/100 y registró una alerta crítica por "
            f"vulneración de línea roja institucional ({detalle_lr}), lo que compromete la consistencia estratégica."
        )
        foco = "Priorizar la disciplina de delimitación institucional para evitar admisiones o especulaciones prohibidas."
        oportunidades = [
            f"Corregir de inmediato la vulneración de línea roja detectada ({detalle_lr}).",
            brecha_juez,
            "Sostener el mensaje clave institucional sin ceder ante preguntas especulativas.",
        ]
        prioridad = "Delimitación institucional"
        hallazgo_desc = (
            "Cruzar una línea roja desplaza el foco informativo hacia el riesgo legal o reputacional y "
            "anula el efecto de los mensajes clave."
        )
        formula = (
            "Ese aspecto específico se encuentra en verificación técnica y no corresponde adelantar juicios; "
            "lo que sí está confirmado en este momento son las medidas inmediatas de atención y control."
        )
    elif score_global < 50.0:
        diagnostico = (
            f"La intervención alcanzó {score_global:.1f}/100, evidenciando brechas estructurales en pertinencia, "
            "control del mensaje o fluidez expositiva que requieren consolidación prioritaria."
        )
        foco = "Consolidar la estructura básica de respuesta directa antes de incorporar giros avanzados."
        oportunidades = [
            brecha_juez,
            "Incorporar explícitamente los mensajes clave del escenario en cada turno.",
            "Mantener estabilidad vocal y contacto visual sostenido frente a cámara.",
        ]
        prioridad = "Conducción estratégica"
        hallazgo_desc = "Sin delimitación clara del núcleo de la pregunta, la vocería pierde credibilidad ante la audiencia."
        formula = "Secuencia VISUM en 3 pasos: 1) Reconocer el impacto -> 2) Explicar certezas -> 3) Detallar acciones en curso."
    else:
        diagnostico = (
            f"Desempeño evaluado con {score_global:.1f}/100 conforme a los estándares de comunicación de crisis VISUM, "
            "mostrando competencias funcionales con margen de evolución en conducción estratégica."
        )
        foco = "Evolucionar de responder correctamente a conducir activamente la conversación con mensajes clave."
        oportunidades = [
            brecha_juez,
            "Reforzar cierres concisos orientados a acciones verificables.",
        ]
        prioridad = "Conducción estratégica"
        hallazgo_desc = "El equilibrio entre precisión fáctica, empatía y aplomo escénico sostiene la confianza pública."
        formula = "Secuencia VISUM en 3 pasos: 1) Reconocer el impacto -> 2) Explicar certezas -> 3) Detallar acciones en curso."

    fallback_obj = InformeVisumResponse(
        sintesis_ejecutiva={
            "diagnostico_general": diagnostico,
            "fortaleza_principal": fortaleza_juez,
            "foco_desarrollo": foco,
            "continuidad_recomendada": rec_juez,
        },
        desempeno_observado={
            "evaluacion_general": diagnostico,
            "fortalezas": [fortaleza_juez],
            "oportunidades_desarrollo": oportunidades,
            "formula_practica_recomendada": formula,
        },
        hallazgos_transversales=[
            {
                "prioridad": prioridad,
                "descripcion": hallazgo_desc,
            }
        ],
        recomendaciones_proximas_vocerias=[
            "Delimitar el núcleo de la pregunta antes de transicionar al mensaje clave.",
            rec_juez,
        ],
        consideracion_final="Comunicar bien en crisis es una disciplina entrenable mediante práctica deliberada.",
        observacion_senal_cruzada=(
            "Se recomienda alinear de forma consistente el aplomo corporal y el ritmo de voz con la disciplina verbal del mensaje."
        ),
    )
    return fallback_obj.model_dump()


def generate_visum_report(
    client: OpenAI,
    model_name: str,
    scenario_info: Dict[str, Any],
    consolidated_json: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Genera la narrativa ejecutiva VISUM en una llamada estructurada, anclada al dictamen del Juez y a las bandas de la rúbrica.
    """
    evaluacion_areas = consolidated_json.get("evaluacion_areas")
    metrics = consolidated_json.get("metrics", {})
    judge_raw = consolidated_json.get("dictamen_juez") or metrics.get("judge") or {}

    if not evaluacion_areas:
        vision = metrics.get("vision", {})
        audio = metrics.get("audio", {})
        puntuacion = consolidated_json.get("puntuacion_global", {})
        rec_af = judge_raw.get("reconocimiento_afectados") or {}

        evaluacion_areas = {
            "expresion": {
                "score": puntuacion.get("score_comunicacion_no_verbal", 75.0),
                "contacto_visual_pct": vision.get("eye_contact_percentage", vision.get("eye_contact_pct", 80.0)),
                "postura_score": vision.get("average_posture_score", vision.get("shoulder_stability_score", 90.0)),
            },
            "tono_voz": {
                "score": puntuacion.get("score_comunicacion_verbal", 80.0),
                "wpm_global": audio.get("wpm_global", audio.get("wpm", 130)),
                "muletillas_count": audio.get("fillers_count", len(audio.get("muletillas_detectadas", []))),
                "pausas_prolongadas": audio.get("pausas_prolongadas", audio.get("silence_pauses", 0)),
            },
            "contenido": {
                "score": puntuacion.get("score_estrategia_crisis", 75.0),
                "adherencia_mensajes_score": judge_raw.get("key_message_adherence_score", 80),
                "control_crisis_score": judge_raw.get("crisis_control_score", 75),
                "bridging_detectado": judge_raw.get("bridging_detected", False),
            },
            "empatia": {
                "score": puntuacion.get("score_empatia", puntuacion.get("score_estrategia_crisis", 75.0)),
                "reconocimiento_afectados_nivel": rec_af.get("nivel", 3) if isinstance(rec_af, dict) else 3,
                "reconocimiento_afectados_criterio": rec_af.get("criterio", "") if isinstance(rec_af, dict) else "",
            },
        }

    raw_score_global = consolidated_json.get("score_global")
    if raw_score_global is None:
        raw_score_global = consolidated_json.get("puntuacion_global", {}).get("score_general")
    score_global = float(raw_score_global if raw_score_global is not None else 75.0)

    transcript = (
        consolidated_json.get("transcript")
        or consolidated_json.get("transcripcion")
        or "Declaración institucional del vocero en ejercicio de crisis."
    )

    dialogue_turns = consolidated_json.get("dialogue_turns") or []
    judge_summary = _summarize_judge_for_visum(judge_raw)
    infraccion_lr = bool(judge_summary.get("infraccion_linea_roja", False))
    evidencia_lr = judge_summary.get("evidencia_linea_roja")
    tramo = compute_performance_tier(score_global, infraccion_lr)
    bandas_rubrica = consolidated_json.get("bandas_rubrica") or {}

    prompt_payload: Dict[str, Any] = {
        "escenario": {
            "titulo": scenario_info.get("title") or scenario_info.get("name") or "Simulación de Vocería en Crisis",
            "contexto": scenario_info.get("context") or scenario_info.get("scenario_description") or "Contingencia operacional y reputacional de alto impacto mediático.",
            "optica": scenario_info.get("optics") or "empática, institucional y rigurosa",
            "audiencia": scenario_info.get("audience") or "opinión pública y medios de comunicación",
            "dificultad": scenario_info.get("difficulty") or "intermediate",
            "mensajes_clave": scenario_info.get("key_messages") or ["La prioridad absoluta es la seguridad de las personas y el restablecimiento del servicio."],
            "lineas_rojas": scenario_info.get("red_lines") or ["No especular sobre causas no confirmadas ni desviar la responsabilidad institucional."],
        },
        "metricas_consolidadas": {
            "score_global": score_global,
            "tramo_desempeno": tramo,
            "expresion_no_verbal": evaluacion_areas.get("expresion", {}),
            "tono_de_voz": evaluacion_areas.get("tono_voz", {}),
            "contenido_estrategico": evaluacion_areas.get("contenido", {}),
            "empatia_congruencia": evaluacion_areas.get("empatia", {}),
        },
        **(
            {"bandas_rubrica": bandas_rubrica}
            if bandas_rubrica
            else {}
        ),
        **(
            {"dictamen_juez_contenido": judge_summary}
            if judge_summary
            else {}
        ),
        **(
            {
                "dialogo_por_turnos": [
                    {
                        "turno": t.get("turnIndex"),
                        "tipo": "contrapregunta" if t.get("turnKind") == "follow_up" else "pregunta_base",
                        "pregunta_base_num": t.get("baseSequenceNo"),
                        "motivo_contrapregunta_ia": resolve_turn_followup_reason(t, dialogue_turns),
                        "duracion_respuesta_seg": t.get("durationSeconds"),
                        "periodista": t.get("questionText"),
                        "vocero": t.get("transcript"),
                        **({"evaluacion_turno": t["evaluation"]} if t.get("evaluation") else {}),
                        **({"voz_turno": t["voiceMetrics"]} if t.get("voiceMetrics") else {}),
                        **({"vision_turno": t["visionMetrics"]} if t.get("visionMetrics") else {}),
                    }
                    for t in dialogue_turns
                ]
            }
            if dialogue_turns
            else {}
        ),
        "transcripcion": transcript,
    }

    user_message = (
        "Redacta el Informe Ejecutivo VISUM respetando estrictamente los puntajes, bandas de rúbrica, "
        "evidencias textuales y el dictamen del Juez de Contenido incluidos en el siguiente expediente consolidado:\n\n"
        f"{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_VISUM},
        {"role": "user", "content": user_message},
    ]

    fast_model = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
    models_to_try = [(model_name, "low")]
    if fast_model and fast_model != model_name:
        models_to_try.append((fast_model, "low"))

    last_error: Optional[Exception] = None

    for target_model, effort in models_to_try:
        for attempt in range(1, 3):
            try:
                # 1. Intentar Structured Outputs vía beta.chat.completions.parse
                if hasattr(client, "beta") and hasattr(client.beta, "chat"):
                    completion = client.beta.chat.completions.parse(
                        model=target_model,
                        messages=messages,
                        temperature=0.3,
                        response_format=InformeVisumResponse,
                        extra_body={"reasoning_effort": effort},
                    )
                    parsed_obj = completion.choices[0].message.parsed
                    if isinstance(parsed_obj, InformeVisumResponse):
                        return parsed_obj.model_dump()
            except Exception as parse_err:
                last_error = parse_err
                err_str = str(parse_err).lower()
                is_transient = (
                    "503" in err_str
                    or "504" in err_str
                    or "429" in err_str
                    or "high demand" in err_str
                    or "timeout" in err_str
                )
                if is_transient:
                    if attempt == 1:
                        logger.warning(
                            f"Aviso transitorio con {target_model} en VISUM ({type(parse_err).__name__}): {parse_err}. "
                            "Esperando 2.5s antes de reintentar para liberar ventana de ráfaga..."
                        )
                        time.sleep(2.5)
                        continue
                    logger.warning(f"Persiste error transitorio en VISUM con {target_model}: {parse_err}")
                    break

            # 2. Respaldo compatible con response_format={"type": "json_object"} + validación Pydantic
            try:
                response = client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    extra_body={"reasoning_effort": effort},
                )
                raw_content = response.choices[0].message.content or ""
                if raw_content.strip():
                    parsed_dict = _parse_llm_json(raw_content)
                    validated = InformeVisumResponse.model_validate(parsed_dict)
                    return validated.model_dump()
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_transient = (
                    "503" in err_str
                    or "504" in err_str
                    or "429" in err_str
                    or "high demand" in err_str
                    or "timeout" in err_str
                )
                if is_transient and attempt == 1:
                    logger.warning(
                        f"Aviso transitorio con {target_model} en VISUM ({type(e).__name__}): {e}. "
                        "Esperando 2.5s antes de reintentar para liberar ventana de ráfaga..."
                    )
                    time.sleep(2.5)
                    continue
                logger.warning(f"Fallo en generación de informe VISUM con {target_model} (intento {attempt}): {e}")
                break

    logger.error(
        f"[ALERTA CRÍTICA] Fallo definitivo en la generación del informe VISUM tras reintentos: {last_error}. "
        "Activando estructura de salvaguarda determinista alineada a la rúbrica."
    )
    return _build_emergency_visum_fallback(
        score_global=score_global,
        infraccion_linea_roja=infraccion_lr,
        evidencia_linea_roja=evidencia_lr,
        judge_summary=judge_summary,
    )
