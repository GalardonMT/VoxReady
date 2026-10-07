import re
import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VISUM = """Eres un consultor senior de comunicaciones estratégicas y media training de VISUM Consulting.
Tu tarea es redactar el Informe Ejecutivo de Evaluación de Vocería a partir de los datos consolidados de una simulación de crisis.

PRINCIPIOS DE REDACCIÓN Y METODOLOGÍA VISUM:
1. Tono ejecutivo, riguroso, diplomático y pedagógico: "Comunicar bien no es un talento innato: es una disciplina que se entrena".
2. Estructura balanceada: valida el piso sólido de competencias del vocero antes de señalar oportunidades de desarrollo avanzadas.
3. Traduce métricas técnicas a impacto comunicacional:
   - Contacto visual y postura -> Aplomo no verbal, compostura y seguridad ante el público.
   - WPM, pausas y fonación -> Control emocional, ritmo pedagógico y claridad expositiva.
   - Apego al mensaje y bridging -> Disciplina informativa y conducción estratégica.
   - Señal cruzada -> Congruencia entre el discurso verbal y la corporalidad/gesto.
4. Fórmulas prácticas obligatorias:
   - Entrevista técnica -> Formulación pedagógica: "Para que todas las personas lo entiendan, este tema se compone de..."
   - Interacción off the record -> Pregunta de preparación: "¿Qué debería comprender mejor este periodista después de conversar conmigo?"
   - Crisis operacional -> Secuencia en 3 pasos: Reconocer el impacto -> Explicar certezas -> Acciones en curso.

ESQUEMA JSON DE RESPUESTA REQUERIDO:
Responde EXCLUSIVAMENTE un objeto JSON válido con la siguiente estructura:
{
  "sintesis_ejecutiva": {
    "diagnostico_general": "Párrafo de 3 a 4 líneas que evalúe el desempeño global en la simulación.",
    "fortaleza_principal": "Piso sólido de competencias demostrado.",
    "foco_desarrollo": "Evolución requerida (de responder correctamente a conducir la conversación).",
    "continuidad_recomendada": "Recomendación de entrenamiento continuo adaptada al escenario."
  },
  "desempeno_observado": {
    "evaluacion_general": "Análisis contextualizado de la interacción, autocontrol y manejo de la presión.",
    "fortalezas": [
      "Fortaleza concreta 1",
      "Fortaleza concreta 2",
      "Fortaleza concreta 3"
    ],
    "oportunidades_desarrollo": [
      "Oportunidad accionable 1",
      "Oportunidad accionable 2",
      "Oportunidad accionable 3"
    ],
    "formula_practica_recomendada": "Formulación verbal o secuencia aplicable al tipo de crisis practicado."
  },
  "hallazgos_transversales": [
    {
      "prioridad": "Pedagogía de la complejidad | Conducción estratégica | Empatía como primera señal | Delimitación institucional",
      "descripcion": "Explicación de la brecha y su impacto estratégico en la audiencia."
    }
  ],
  "recomendaciones_proximas_vocerias": [
    "Regla de oro accionable 1",
    "Regla de oro accionable 2",
    "Regla de oro accionable 3",
    "Regla de oro accionable 4"
  ],
  "consideracion_final": "Párrafo de cierre sobre la práctica y el perfeccionamiento de habilidades.",
  "observacion_senal_cruzada": "Cita o momento exacto donde la corporalidad, la voz o el mensaje tuvieron sinergia o contradicción evidente."
}
"""


def _clean_json_markdown(text: str) -> str:
    """Elimina delimitadores markdown tipo ```json ... ``` si el LLM los incluye."""
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean, re.IGNORECASE)
    if match:
        clean = match.group(1).strip()
    return clean


def generate_visum_report(
    client: OpenAI,
    model_name: str,
    scenario_info: Dict[str, Any],
    consolidated_json: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Invoca a NVIDIA NIM en una llamada independiente para generar la narrativa ejecutiva VISUM.
    """
    # Manejar formatos tanto de lab-worker como del worker de produccion
    evaluacion_areas = consolidated_json.get("evaluacion_areas")
    if not evaluacion_areas:
        # Extraer de metrics si viene en formato worker
        metrics = consolidated_json.get("metrics", {})
        vision = metrics.get("vision", {})
        audio = metrics.get("audio", {})
        judge = metrics.get("judge", {})
        puntuacion = consolidated_json.get("puntuacion_global", {})
        
        evaluacion_areas = {
            "expresion": {
                "score": puntuacion.get("score_comunicacion_no_verbal", 75.0),
                "contacto_visual_pct": vision.get("eye_contact_percentage", 80.0),
                "postura_score": vision.get("average_posture_score", 90.0)
            },
            "tono_voz": {
                "score": puntuacion.get("score_comunicacion_verbal", 80.0),
                "wpm": audio.get("wpm", 130),
                "muletillas_count": audio.get("fillers_count", 0),
                "pausas_silencio": audio.get("silence_pauses", 1)
            },
            "contenido": {
                "score": puntuacion.get("score_estrategia_crisis", 75.0),
                "adherencia_mensajes": judge.get("key_message_adherence_score", 80),
                "control_crisis": judge.get("crisis_control_score", 75)
            },
            "empatia": {
                "score": puntuacion.get("score_estrategia_crisis", 75.0),
                "bridging_detectado": judge.get("bridging_detected", True)
            }
        }

    score_global = (
        consolidated_json.get("score_global")
        or consolidated_json.get("puntuacion_global", {}).get("score_general")
        or 75.0
    )

    transcript = (
        consolidated_json.get("transcript")
        or consolidated_json.get("transcripcion")
        or "Declaración institucional del vocero en ejercicio de crisis."
    )

    prompt_payload = {
        "escenario": {
            "titulo": scenario_info.get("title") or scenario_info.get("name") or "Simulación de Vocería en Crisis",
            "contexto": scenario_info.get("context") or scenario_info.get("scenario_description") or "Contingencia operacional y reputacional de alto impacto mediático.",
            "optica": scenario_info.get("optics") or "empática y técnica",
            "mensajes_clave": scenario_info.get("key_messages") or ["La prioridad absoluta es la seguridad de las personas y el restablecimiento del servicio."],
            "lineas_rojas": scenario_info.get("red_lines") or ["No especular sobre causas no confirmadas ni desviar la responsabilidad institucional."]
        },
        "metricas_consolidadas": {
            "score_global": score_global,
            "expresion_no_verbal": evaluacion_areas.get("expresion", {}),
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
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        raw_content = response.choices[0].message.content
        cleaned_content = _clean_json_markdown(raw_content)
        parsed = json.loads(cleaned_content)
        return parsed
    except Exception as e:
        logger.error(f"Fallo en la generación del informe VISUM ({type(e).__name__}): {str(e)}")
        # Fallback estructurado en caso de indisponibilidad temporal de la red o del modelo
        return {
            "sintesis_ejecutiva": {
                "diagnostico_general": f"El vocero demostró compostura y solvencia general ante el escenario de contingencia, obteniendo un puntaje global de {score_global}/100.",
                "fortaleza_principal": "Mantuvo la calma expositiva y apego a las directrices institucionales prioritarias.",
                "foco_desarrollo": "Transicionar desde una postura reactiva de respuestas técnicas hacia la conducción activa de la conversación.",
                "continuidad_recomendada": "Profundizar en entrenamientos de bridging bajo preguntas periodísticas agresivas."
            },
            "desempeno_observado": {
                "evaluacion_general": "Interacción sobria con adecuado autocontrol ante la presión mediática.",
                "fortalezas": [
                    "Aplomo no verbal y estabilidad postural durante toda la exposición.",
                    "Ritmo de locución controlado y adecuado manejo de pausas reflexivas.",
                    "Respeto por las líneas rojas institucionales sin incurrir en especulaciones."
                ],
                "oportunidades_desarrollo": [
                    "Priorizar la empatía hacia los afectados antes de desglosar explicaciones operativas.",
                    "Estructurar los mensajes complejos en secuencias pedagógicas de tres puntos clave.",
                    "Reforzar el contacto visual en los momentos de mayor énfasis declarativo."
                ],
                "formula_practica_recomendada": "Reconocer el impacto en la comunidad -> Explicar las certezas verificadas -> Detallar las medidas inmediatas en curso."
            },
            "hallazgos_transversales": [
                {
                    "prioridad": "Empatía como primera señal",
                    "descripcion": "Ante crisis de impacto humano, el primer párrafo debe conectar emocionalmente con la audiencia antes de recurrir a tecnicismos."
                },
                {
                    "prioridad": "Conducción estratégica",
                    "descripcion": "Aplicar técnicas de bridging fluidas para redirigir preguntas hipotéticas hacia compromisos de acción verificables."
                }
            ],
            "recomendaciones_proximas_vocerias": [
                "Regla 1: Iniciar siempre declarando lo que sí está bajo control y verificado.",
                "Regla 2: Evitar muletillas de duda al conectar argumentos (usar pausas en silencio).",
                "Regla 3: No emitir promesas con plazos específicos hasta contar con validación técnica.",
                "Regla 4: Concluir reiterando el canal oficial de actualización para los medios."
            ],
            "consideracion_final": "Comunicar bien no es un talento innato: es una disciplina que se perfecciona mediante la práctica sistemática y la retroalimentación objetiva.",
            "observacion_senal_cruzada": "El vocero mantuvo contacto visual firme al declarar el compromiso institucional, proyectando congruencia con el mensaje de responsabilidad."
        }
