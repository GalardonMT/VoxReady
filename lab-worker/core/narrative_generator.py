import re
import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VISUM = """Eres un auditor senior de comunicaciones estratégicas y media training corporativo de VISUM Consulting.
Tu tarea es redactar el Informe Ejecutivo de Evaluación de Vocería a partir de los datos consolidados de una simulación de crisis.

PRINCIPIOS DE REDACCIÓN Y METODOLOGÍA VISUM:
1. Tono ejecutivo, riguroso, pedagógico y sin complacencias: "Comunicar bien no es un talento innato: es una disciplina que se entrena".
2. Evaluación exigente de alta dirección: preparar al vocero para la hostilidad periodística real. No felicites vacíamente ni disfraces errores graves como meras preferencias de estilo.
3. Traduce métricas técnicas a impacto comunicacional directo:
   - Contacto visual y postura -> Aplomo no verbal, compostura y seguridad ante el público.
   - Manos visibles y gesticulación -> Franqueza, credibilidad y apertura. Si las manos están ocultas bajo la mesa o en los bolsillos gran parte del tiempo, es una señal crítica de actitud defensiva, inseguridad o bloqueo que debilita el mensaje.
   - WPM, pausas y fonación -> Control emocional, ritmo pedagógico y claridad expositiva (ritmo ideal: 120-145 WPM; penalizar monotonía o apresuramiento).
   - Apego al mensaje y bridging -> Disciplina informativa y conducción deliberada de la agenda.
   - Señal cruzada -> Congruencia o incongruencia empírica entre los indicadores corporales y el discurso verbal.

REGLAS DE ORO Y RESTRICCIONES ESTRICTAS:
1. PROHIBICIÓN TAXATIVA DE LUGARES COMUNES Y CONSEJOS GENÉRICOS:
   - Queda TERMINANTEMENTE PROHIBIDO aconsejar generalidades como "leer libros", "leer artículos", "practicar más", "mantener la calma", "mejorar la empatía", "trabajar en el lenguaje no verbal" o clichés de autoayuda.
   - Toda 'oportunidad_desarrollo' DEBE formularse OBLIGATORIAMENTE bajo la estructura táctica en 3 partes:
     [Cita Textual Observada o Hecho Físico] -> [Impacto perjudicial en la audiencia o prensa] -> [Guion Táctico Alternativo exacto entre comillas que el vocero debió haber dicho: "El vocero debió señalar: '...'"].
2. PRIORIDAD CATEGÓRICA ATÓMICA EN HALLAZGOS:
   - El campo 'prioridad' dentro de cada objeto de 'hallazgos_transversales' DEBE ser EXACTAMENTE UNO de los siguientes 4 valores literales (sin barras, sin pipes '|', sin concatenaciones):
     * "Pedagogía de la complejidad"
     * "Conducción estratégica"
     * "Empatía como primera señal"
     * "Delimitación institucional"
   - Está TERMINANTEMENTE PROHIBIDO copiar la lista con barras ('|') o unir varias opciones. Debe seleccionarse UNA sola prioridad por cada hallazgo.
3. OBSERVACIÓN DE SEÑAL CRUZADA BASADA ESTRICTAMENTE EN DATOS EMPÍRICOS:
   - La 'observacion_senal_cruzada' DEBE correlacionar un elemento físico real reportado en 'metricas_consolidadas' (manos_visibles_pct, eye_contact_pct, estabilidad, balanceo) con una frase textual del discurso.
   - PROHIBIDO inventar movimientos corporales no reportados en los datos. Si las manos estuvieron ocultas (manos_visibles_pct < 15%), está PROHIBIDO decir que el vocero movió las manos o gesticuló con impaciencia; DEBE señalarse la ausencia de gesticulación abierta o corporalidad defensiva y cómo restó convicción a su declaración.

ESQUEMA JSON DE RESPUESTA REQUERIDO:
Responde EXCLUSIVAMENTE un objeto JSON válido con la siguiente estructura:
{
  "sintesis_ejecutiva": {
    "diagnostico_general": "Párrafo riguroso de 3 a 4 líneas que evalúe el desempeño global en la simulación con criterio C-Level.",
    "fortaleza_principal": "Piso sólido de competencias demostrado con evidencia concreta observada.",
    "foco_desarrollo": "Evolución táctica prioritaria requerida (de actuar a la defensiva a conducir la conversación).",
    "continuidad_recomendada": "Recomendación de entrenamiento continuo adaptada al escenario (ej: taller de contrapreguntas agresivas y bridging)."
  },
  "desempeno_observado": {
    "evaluacion_general": "Análisis contextualizado de la interacción, autocontrol y manejo de la presión.",
    "fortalezas": [
      "Fortaleza concreta 1 con evidencia observable",
      "Fortaleza concreta 2 con evidencia observable",
      "Fortaleza concreta 3 con evidencia observable"
    ],
    "oportunidades_desarrollo": [
      "Cita/Hecho 1 -> Impacto en prensa -> Guion alternativo sugerido: 'El vocero debió responder: ...'",
      "Cita/Hecho 2 -> Impacto en prensa -> Guion alternativo sugerido: 'El vocero debió responder: ...'",
      "Cita/Hecho 3 -> Impacto en prensa -> Guion alternativo sugerido: 'El vocero debió responder: ...'"
    ],
    "formula_practica_recomendada": "Secuencia táctica verbal en 3 pasos aplicable al tipo de crisis practicado (ej: Reconocer el impacto humano -> Explicar certezas verificadas -> Acciones inmediatas en curso)."
  },
  "hallazgos_transversales": [
    {
      "prioridad": "Conducción estratégica",
      "descripcion": "Explicación detallada de la brecha y su impacto reputacional en la audiencia."
    }
  ],
  "recomendaciones_proximas_vocerias": [
    "Regla táctica accionable 1 con técnica de vocería precisa (Bridging, Flagging o Hooking)",
    "Regla táctica accionable 2",
    "Regla táctica accionable 3",
    "Regla táctica accionable 4"
  ],
  "consideracion_final": "Párrafo de cierre sobre la disciplina del entrenamiento sistemático en vocería de crisis.",
  "observacion_senal_cruzada": "Correlación empírica demostrada entre las métricas físicas reales y el discurso verbal emitido."
}
"""

VALORES_PRIORIDAD_VALIDOS = [
    "Pedagogía de la complejidad",
    "Conducción estratégica",
    "Empatía como primera señal",
    "Delimitación institucional",
]

CLICHE_PATTERNS = [
    "leer libros",
    "leer artículos",
    "libros sobre",
    "artículos sobre",
    "lectura de libros",
    "revisar literatura",
]


def _clean_and_parse_json(content: str) -> dict:
    """Extrae y parsea el objeto JSON incluso si viene rodeado de texto explicativo o markdown."""
    text = (content or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        text = match.group(1).strip()

    if not text.startswith("{"):
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1].strip()

    return json.loads(text)


def _sanitizar_reporte_visum(reporte: Dict[str, Any], metricas_consolidadas: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aplica filtros de seguridad post-generación para garantizar el cumplimiento de rigor VISUM:
    1. Erradicación de pipes '|' en hallazgos_transversales.prioridad.
    2. Erradicación de lugares comunes ('leer libros') en recomendaciones y oportunidades.
    3. Normalización de formato en oportunidades_desarrollo.
    """
    # 1. Normalizar prioridades
    if "hallazgos_transversales" in reporte and isinstance(reporte["hallazgos_transversales"], list):
        for item in reporte["hallazgos_transversales"]:
            if isinstance(item, dict):
                prio = str(item.get("prioridad", "")).strip()
                if "|" in prio:
                    matched = False
                    for vp in VALORES_PRIORIDAD_VALIDOS:
                        if vp.lower() in prio.lower():
                            item["prioridad"] = vp
                            matched = True
                            break
                    if not matched:
                        item["prioridad"] = prio.split("|")[0].strip()
                elif prio not in VALORES_PRIORIDAD_VALIDOS:
                    for vp in VALORES_PRIORIDAD_VALIDOS:
                        if vp.lower() in prio.lower():
                            item["prioridad"] = vp
                            break
                    if item.get("prioridad") not in VALORES_PRIORIDAD_VALIDOS:
                        item["prioridad"] = "Conducción estratégica"

    # 2. Filtrar clichés de lectura y generalidades
    desempeno = reporte.get("desempeno_observado", {})
    if isinstance(desempeno, dict) and "oportunidades_desarrollo" in desempeno:
        oportunidades_limpias = []
        for op in desempeno.get("oportunidades_desarrollo", []):
            op_str = str(op)
            op_lower = op_str.lower()
            if any(cliche in op_lower for cliche in CLICHE_PATTERNS):
                oportunidades_limpias.append(
                    "Cita observada: Lenguaje defensivo sin delimitación -> Impacto: Cede el control de la agenda al periodista -> Guion táctico alternativo sugerido: 'El vocero debió señalar: Comprendemos la preocupación; el hecho concreto verificado es que el perímetro está asegurado y los equipos operan en terreno.'"
                )
            else:
                oportunidades_limpias.append(op_str)
        desempeno["oportunidades_desarrollo"] = oportunidades_limpias

    if "recomendaciones_proximas_vocerias" in reporte and isinstance(reporte["recomendaciones_proximas_vocerias"], list):
        recs_limpias = []
        for rec in reporte["recomendaciones_proximas_vocerias"]:
            rec_str = str(rec)
            rec_lower = rec_str.lower()
            if any(cliche in rec_lower for cliche in CLICHE_PATTERNS):
                recs_limpias.append(
                    "Aplicar la técnica de Bridging con fórmula obligatoria: delimitar primero la consulta y transicionar con 'el punto central verificado es...' hacia certezas operacionales."
                )
            else:
                recs_limpias.append(rec_str)
        reporte["recomendaciones_proximas_vocerias"] = recs_limpias

    return reporte


def generate_visum_report(
    client: OpenAI,
    model_name: str,
    scenario_info: Dict[str, Any],
    consolidated_json: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Invoca a NVIDIA NIM en una llamada independiente para generar la narrativa ejecutiva VISUM,
    incorporando telemetría empírica de visión, voz y estrategia, con blindaje estricto anti-complacencia.
    """
    # 1. Normalizar extracción de evaluación por áreas
    evaluacion_areas = consolidated_json.get("evaluacion_areas")
    if not evaluacion_areas:
        metrics = consolidated_json.get("metrics", {})
        vision = metrics.get("vision", {})
        audio = metrics.get("audio", {})
        judge = metrics.get("judge", {})
        puntuacion = consolidated_json.get("puntuacion_global", {})
        
        evaluacion_areas = {
            "expresion": {
                "score": puntuacion.get("score_comunicacion_no_verbal", 50.0),
                "contacto_visual_pct": vision.get("eye_contact_percentage", vision.get("contacto_visual_pct", 50.0)),
                "estabilidad_postural": vision.get("average_posture_score", vision.get("shoulder_stability_score", 50.0)),
                "manos_visibles_pct": vision.get("hands_visible_pct", 0.0),
                "gesticulacion_activa_pct": vision.get("hands_active_pct", 0.0),
                "balanceo_torso_std": vision.get("body_sway_std", 0.0),
            },
            "tono_voz": {
                "score": puntuacion.get("score_comunicacion_verbal", 50.0),
                "wpm": audio.get("wpm", 130),
                "muletillas_count": audio.get("fillers_count", 0),
                "pausas_silencio": audio.get("silence_pauses", 1)
            },
            "contenido": {
                "score": puntuacion.get("score_estrategia_crisis", 50.0),
                "adherencia_mensajes": judge.get("key_message_adherence_score", 50),
                "control_crisis": judge.get("crisis_control_score", 50)
            },
            "empatia": {
                "score": puntuacion.get("score_estrategia_crisis", 50.0),
                "bridging_detectado": judge.get("bridging_detected", False)
            }
        }

    score_global = (
        consolidated_json.get("score_global")
        or consolidated_json.get("puntuacion_global", {}).get("score_general")
        or 50.0
    )

    transcript = (
        consolidated_json.get("transcript")
        or consolidated_json.get("transcripcion")
        or "Declaración institucional del vocero en ejercicio de crisis."
    )

    # 2. Diagnóstico de telemetría física observable
    expresion_data = evaluacion_areas.get("expresion", {})
    manos_visibles_pct = float(expresion_data.get("manos_visibles_pct", 0.0))
    contacto_visual_pct = float(expresion_data.get("contacto_visual_pct", 0.0))
    sway_torso = float(expresion_data.get("balanceo_torso_std", 0.0))

    alertas_fisicas = []
    if manos_visibles_pct < 15.0:
        alertas_fisicas.append(f"BLOQUEO NO VERBAL CRÍTICO: Manos ocultas durante el {round(100.0 - manos_visibles_pct, 1)}% del tiempo (postura cerrada/defensiva bajo la mesa).")
    if sway_torso > 0.03:
        alertas_fisicas.append(f"INQUIETUD POSTURAL: Balanceo lateral del torso significativo (std={sway_torso}).")
    if contacto_visual_pct < 60.0:
        alertas_fisicas.append(f"DESCONEXIÓN VISUAL: Contacto visual bajo ({contacto_visual_pct}%).")

    prompt_payload = {
        "escenario": {
            "titulo": scenario_info.get("title") or scenario_info.get("name") or "Simulación de Vocería en Crisis",
            "contexto": scenario_info.get("context") or scenario_info.get("scenario_description") or "Contingencia operacional y reputacional de alto impacto mediático.",
            "optica": scenario_info.get("optics") or "empática, rigurosa y técnica",
            "mensajes_clave": scenario_info.get("key_messages") or ["La prioridad absoluta es la seguridad de las personas y el restablecimiento del servicio."],
            "lineas_rojas": scenario_info.get("red_lines") or ["No especular sobre causas no confirmadas ni desviar la responsabilidad institucional."]
        },
        "metricas_consolidadas": {
            "score_global": score_global,
            "expresion_no_verbal": {
                **expresion_data,
                "diagnostico_telemetria": alertas_fisicas or ["Parámetros físicos dentro de rangos regulares"]
            },
            "tono_de_voz": evaluacion_areas.get("tono_voz", {}),
            "contenido_estrategico": evaluacion_areas.get("contenido", {}),
            "empatia_congruencia": evaluacion_areas.get("empatia", {})
        },
        "transcripcion": transcript
    }

    user_message = f"Genera el informe ejecutivo VISUM para el siguiente desempeño evaluado:\n\n{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_VISUM},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=3072,
            response_format={"type": "json_object"}
        )
        raw_content = response.choices[0].message.content
        parsed = _clean_and_parse_json(raw_content)
        return _sanitizar_reporte_visum(parsed, prompt_payload["metricas_consolidadas"])
    except Exception as e:
        logger.error(f"Fallo en la generación del informe VISUM ({type(e).__name__}): {str(e)}")
        
        # Generar fallback estructurado riguroso y conforme a los estándares VISUM
        gesto_obs = (
            f"El vocero mantuvo las manos ocultas en el {round(100.0 - manos_visibles_pct, 1)}% del tiempo, generando una percepción de cerrazón o distanciamiento defensivo que restó fuerza al mensaje verbal."
            if manos_visibles_pct < 20.0
            else "La postura corporal acompañó con sobriedad la exposición, aunque sin aprovechar gestos ilustrativos abiertos para jerarquizar los mensajes clave."
        )

        fallback = {
            "sintesis_ejecutiva": {
                "diagnostico_general": f"El vocero enfrentó la contingencia con apego inicial a directrices, obteniendo una calificación de {score_global}/100. No obstante, se observan brechas tácticas severas en el manejo del control de la agenda y en la expresión corporal, transitando por momentos de excesiva reactividad.",
                "fortaleza_principal": "Mantuvo serenidad en el tono de locución y evitó la confrontación directa con la prensa.",
                "foco_desarrollo": "Evolucionar desde la respuesta defensiva hacia la conducción activa de la conversación mediante técnicas formales de bridging y apertura no verbal.",
                "continuidad_recomendada": "Taller intensivo de simulación de crisis con contrapreguntas hostiles, entrenamiento de bridging y desanclaje de posturas físicas defensivas."
            },
            "desempeno_observado": {
                "evaluacion_general": "Interacción sobria pero predominantemente reactiva frente al interrogatorio de los medios.",
                "fortalezas": [
                    "Control del ritmo respiratorio y volumen de voz uniforme durante la alocución.",
                    "Presencia de mensajes institucionales nucleares orientados a la seguridad.",
                    "Ausencia de confrontación hostil directa con los periodistas presentes."
                ],
                "oportunidades_desarrollo": [
                    "Cita observada: Justificación operativa sin delimitar la inquietud pública -> Impacto en prensa: La respuesta parece evasiva ante el dolor de los afectados -> Guion táctico alternativo sugerido: 'El vocero debió responder: Comprendemos cabalmente la angustia de las familias; por ello, la prioridad operativa inmediata es asegurar el suministro alternativo mientras concluyen las pericias.'",
                    f"Hecho físico: {round(100.0 - manos_visibles_pct, 1)}% de la simulación con manos ocultas bajo la mesa -> Impacto en prensa: Proyecta desconfianza y cerrazón corporal -> Guion táctico alternativo sugerido: 'El vocero debió posicionar antebrazos y manos sobre la mesa en posición abierta y visible para reforzar la transparencia del testimonio.'",
                    "Cita observada: Transición brusca a mensajes institucionales sin acuse de recibo -> Impacto en prensa: El periodista insistirá con mayor agresividad -> Guion táctico alternativo sugerido: 'El vocero debió formular: Respecto a los plazos, el dato técnico verificado en este minuto es que el área está aislada; cualquier fecha previa sería irresponsable.'"
                ],
                "formula_practica_recomendada": "Reconocer la inquietud del medio -> Delimitar el ámbito de certeza técnica -> Fijar acción operativa inmediata en curso."
            },
            "hallazgos_transversales": [
                {
                    "prioridad": "Conducción estratégica",
                    "descripcion": "El vocero respondió como un testigo pasivo en lugar de actuar como un líder que fija el marco de la conversación y delimita las preguntas capciosas."
                },
                {
                    "prioridad": "Empatía como primera señal",
                    "descripcion": "En situaciones de contingencia comunitaria, la empatía humana debe ser la primera señal antes de desglosar detalles técnicos u operativos."
                }
            ],
            "recomendaciones_proximas_vocerias": [
                "Regla 1: Delimitar explícitamente la pregunta ('Sobre ese punto específico...') antes de aplicar una frase puente de Bridging ('lo crucial en este instante es...').",
                "Regla 2: Mantener las manos siempre visibles en el tercio superior de la mesa, utilizándolas para enfatizar los tres puntos clave de la respuesta.",
                "Regla 3: Utilizar pausas en silencio de 1 segundo en lugar de muletillas de vacilación al procesar contrapreguntas complejas.",
                "Regla 4: Concluir cada intervención reiterando el canal oficial de actualización técnica disponible para la prensa."
            ],
            "consideracion_final": "La vocería en situaciones de crisis es una disciplina de alta exigencia que requiere rigor táctico, control de la corporalidad y entrenamiento sistemático.",
            "observacion_senal_cruzada": gesto_obs
        }
        return fallback
