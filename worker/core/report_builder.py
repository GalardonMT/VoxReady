import datetime
from typing import Dict, Any, Optional


def calculate_expression_area_score(vision_summary: dict) -> dict:
    """
    Calcula el puntaje de 0 a 100 para el área 'expression' según los criterios de VISUM:
    - Contacto visual: 40%
    - Estabilidad corporal y postura: 30%
    - Gesticulación (visibilidad y actividad de manos): 30%
    """
    eye_pct = float(vision_summary.get("eye_contact_pct", vision_summary.get("contacto_visual_porcentaje", 0.0)))
    shoulder_score = float(vision_summary.get("shoulder_stability_score", vision_summary.get("posture_stability_score", 100.0)))
    sway_std = float(vision_summary.get("body_sway_std", 0.0))
    hands_vis_pct = float(vision_summary.get("hands_visible_pct", 0.0))
    hands_act_pct = float(vision_summary.get("hands_active_pct", 0.0))

    # 1. Puntuación de postura y estabilidad (penaliza balanceo lateral > 0.04)
    sway_penalty = min(40.0, sway_std * 800.0)
    body_stability_final = max(0.0, shoulder_score - sway_penalty)

    # 2. Puntuación de gesticulación
    # Premia que las manos sean visibles y se usen activamente sin exceso estático
    gesticulation_score = (hands_vis_pct * 0.5) + (hands_act_pct * 0.5)

    # 3. Ponderación interna del área (40% contacto, 30% postura/estabilidad, 30% gesticulación)
    final_expression_score = (
        (eye_pct * 0.40) +
        (body_stability_final * 0.30) +
        (gesticulation_score * 0.30)
    )

    return {
        "score": round(max(0.0, min(100.0, final_expression_score)), 2),
        "metrics": {
            "contacto_visual_pct": eye_pct,
            "estabilidad_postural": round(body_stability_final, 2),
            "manos_visibles_pct": hands_vis_pct,
            "gesticulacion_activa_pct": hands_act_pct,
            "balanceo_torso_std": sway_std
        }
    }


class ReportBuilder:
    """
    Consolidador y fusionador matemático de métricas para la sesión de crisis.
    Integra los resultados de visión, acústica/audio y evaluación de LLM
    en un payload JSON unificado y normalizado.
    """

    @staticmethod
    def build_consolidated_report(
        session_id: str,
        blob_name: str,
        vision_result: Dict[str, Any],
        audio_result: Dict[str, Any],
        llm_result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Extracción de scores parciales
        # Visión: contacto visual, postura y gesticulación (VISUM)
        vision_summary = vision_result.get("summary") or vision_result.get("visum_summary") or vision_result
        contacto_pct = float(vision_summary.get("eye_contact_pct", vision_result.get("contacto_visual_porcentaje", 0.0)))
        postura_score = float(vision_summary.get("shoulder_stability_score", vision_result.get("posture_stability_score", 100.0)))

        if any(k in vision_summary for k in ["hands_visible_pct", "body_sway_std", "shoulder_stability_score"]):
            expression_eval = calculate_expression_area_score(vision_summary)
            score_visual = expression_eval["score"]
        else:
            score_visual = round(max(0.0, min(100.0, (contacto_pct * 0.60) + (postura_score * 0.40))), 1)

        # Audio: fluidez y dicción
        audio_metrics = audio_result.get("metrics", {})
        score_fluidez = float(audio_metrics.get("score_fluidez", 75.0))
        score_diccion = float(audio_metrics.get("score_diccion", 100.0))
        score_verbal = round(max(0.0, min(100.0, (score_fluidez * 0.60) + (score_diccion * 0.40))), 1)

        # LLM: Juez Visum o apego a mensajes
        if "puntaje_global_100" in llm_result:
            score_estrategico = float(llm_result["puntaje_global_100"])
            score_adherencia = float(llm_result.get("dimensiones", {}).get("alineacion_mensaje_clave", {}).get("score_100", score_estrategico))
            score_control = float(llm_result.get("dimensiones", {}).get("tecnicas_control", {}).get("score_100", score_estrategico))
            score_empatia = float(llm_result.get("dimensiones", {}).get("asertividad_hostilidad", {}).get("score_100", 75.0))
        else:
            score_adherencia = float(llm_result.get("key_message_adherence_score", 70.0))
            score_control = float(llm_result.get("crisis_control_score", 70.0))
            score_estrategico = round(max(0.0, min(100.0, (score_adherencia * 0.50) + (score_control * 0.50))), 1)
            score_empatia = 75.0

        # 2. Score Global Compuesto de la Sesión (4 Ejes Oficiales)
        # Expresión 25% | Voz 25% | Coherencia (Estrategia) 35% | Empatía 15%
        score_global = round(
            (score_visual * 0.25) +
            (score_verbal * 0.25) +
            (score_estrategico * 0.35) +
            (score_empatia * 0.15),
            1,
        )

        areas_evaluacion = {
            "expression": score_visual,
            "voice": score_verbal,
            "coherence": score_estrategico,
            "empathy": score_empatia,
        }

        report = {
            "session_id": session_id,
            "blob_name": blob_name,
            "completed_at": now_iso,
            "metadata": metadata or {},
            "puntuacion_global": {
                "score_general": score_global,
                "score_comunicacion_no_verbal": score_visual,
                "score_comunicacion_verbal": score_verbal,
                "score_estrategia_crisis": score_estrategico,
                "score_empatia": score_empatia,
                "areas": areas_evaluacion,
            },
            "evaluacion_llm_crisis": {
                "score_global_visum": score_estrategico,
                "dimensiones_visum": llm_result.get("dimensiones", {}),
                "feedback_pedagogico": llm_result.get("feedback", {}),
                "key_message_adherence_score": score_adherencia,
                "crisis_control_score": score_control,
                "bridging_detected": llm_result.get("bridging_detected", False),
                "strengths": llm_result.get("strengths", []),
                "weaknesses": llm_result.get("weaknesses", []),
                "executive_summary": llm_result.get("executive_summary", ""),
            },
            "metricas_vision": {
                "total_frames_analizados": vision_summary.get("total_frames_analyzed", vision_result.get("total_frames_analizados", 0)),
                "frames_validos": vision_result.get("frames_validos", vision_summary.get("total_frames_analyzed", 0)),
                "contacto_visual_porcentaje": contacto_pct,
                "posture_stability_score": postura_score,
                "hands_visible_pct": vision_summary.get("hands_visible_pct", 0.0),
                "hands_active_pct": vision_summary.get("hands_active_pct", 0.0),
                "body_sway_std": vision_summary.get("body_sway_std", 0.0),
                "shoulder_stability_score": vision_summary.get("shoulder_stability_score", postura_score),
                "eye_contact_pct": contacto_pct,
                "desglose_ejes": vision_result.get("metricas_ejes", {}),
                "eventos_destacados": vision_result.get("eventos_detectados", []),
            },
            "metricas_audio_voz": {
                "duracion_segundos": audio_metrics.get("duracion_segundos", 0.0),
                "tiempo_voz_activa_segundos": audio_metrics.get("tiempo_voz_activa_segundos", 0.0),
                "palabras_totales": audio_metrics.get("palabras_totales", 0),
                "wpm_global": audio_metrics.get("wpm_global", 0.0),
                "wpm_articulacion_neta": audio_metrics.get("wpm_articulacion_neta", 0.0),
                "ratio_fonacion": audio_metrics.get("ratio_fonacion", 0.0),
                "pausas_naturales": audio_metrics.get("pausas_naturales", 0),
                "pausas_vacilacion": audio_metrics.get("pausas_vacilacion", 0),
                "pausas_prolongadas": audio_metrics.get("pausas_prolongadas", 0),
                "detalle_pausas_prolongadas": audio_metrics.get("detalle_pausas_prolongadas", []),
                "densidad_muletillas_pct": audio_metrics.get("densidad_muletillas_pct", 0.0),
                "muletillas_detectadas": audio_metrics.get("muletillas_detectadas", []),
                "conteo_muletillas": audio_metrics.get("conteo_muletillas", {}),
                "score_fluidez": score_fluidez,
                "score_diccion": score_diccion,
            },
            "transcripcion": {
                "texto_completo": audio_result.get("transcription", ""),
                "palabras_con_marcas_tiempo": audio_result.get("words", []),
            },
        }

        return report


def sanitize_report_json(
    session_id: str,
    job_id: Optional[str],
    report_id: Optional[str],
    processed_at: str,
    recording_url: str,
    overall_score: int,
    area_scores: Dict[str, int],
    visum_narrative: Dict[str, Any],
    vision_metrics: Dict[str, Any],
    audio_metrics: Dict[str, Any],
    judge_metrics: Dict[str, Any],
    transcript: str,
    segmented_turns: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Sanea y normaliza el reporte consolidado de acuerdo con la Especificación Técnica (Sección 1):
    1. Elimina informe_ejecutivo_visum de la raíz, preservando únicamente narrative.visum.
    2. Unifica las métricas de visión a estándar técnico en camelCase sin duplicidades en español.
    3. Normaliza métricas acústicas y dimensiones pedagógicas del LLM Juez.
    """
    # 1. Normalizar Visum
    sintesis_ej = visum_narrative.get("sintesis_ejecutiva") or {}
    desempeno = visum_narrative.get("desempeno_observado") or {}
    
    sintesis_clean = {
        "diagnosticoGeneral": sintesis_ej.get("diagnostico_general", sintesis_ej.get("diagnosticoGeneral", "")),
        "fortalezaPrincipal": sintesis_ej.get("fortaleza_principal", sintesis_ej.get("fortalezaPrincipal", "")),
        "focoDesarrollo": sintesis_ej.get("foco_desarrollo", sintesis_ej.get("focoDesarrollo", "")),
        "continuidadRecomendada": sintesis_ej.get("continuidad_recomendada", sintesis_ej.get("continuidadRecomendada", ""))
    }
    
    formula_rec = (
        desempeno.get("formula_practica_recomendada")
        or visum_narrative.get("formulaRecomendada")
        or "Secuencia de 3 pasos: Reconocer el impacto -> Explicar certezas -> Acciones en curso."
    )
    
    hallazgos_raw = visum_narrative.get("hallazgos_transversales") or visum_narrative.get("hallazgosTransversales") or []
    if isinstance(hallazgos_raw, list) and hallazgos_raw:
        hallazgos_str = " ".join([h.get("descripcion", str(h)) if isinstance(h, dict) else str(h) for h in hallazgos_raw])
    else:
        hallazgos_str = str(hallazgos_raw or "")
        
    visum_clean = {
        "sintesisEjecutiva": sintesis_clean,
        "formulaRecomendada": formula_rec,
        "hallazgosTransversales": hallazgos_str,
        # Preservar atributos detallados para vistas pedagógicas profundas
        "sintesis_ejecutiva": sintesis_ej,
        "desempeno_observado": desempeno,
        "recomendaciones_proximas_vocerias": visum_narrative.get("recomendaciones_proximas_vocerias", []),
        "consideracion_final": visum_narrative.get("consideracion_final", "")
    }

    # 2. Normalizar Métricas de Visión
    v_summary = vision_metrics.get("summary") or vision_metrics.get("visum_summary") or vision_metrics
    eye_pct = float(v_summary.get("eye_contact_pct", vision_metrics.get("contacto_visual_porcentaje", 0.0)))
    shoulder_score = float(v_summary.get("shoulder_stability_score", vision_metrics.get("posture_stability_score", vision_metrics.get("average_posture_score", 100.0))))
    sway_std = float(v_summary.get("body_sway_std", 0.0))
    hands_vis = float(v_summary.get("hands_visible_pct", 0.0))
    frames_count = int(v_summary.get("total_frames_analyzed", vision_metrics.get("total_frames_analizados", vision_metrics.get("frames_validos", 0))))

    clean_vision = {
        "eyeContactPct": round(eye_pct, 2),
        "shoulderStabilityScore": round(shoulder_score, 2),
        "bodySwayStd": round(sway_std, 4),
        "handsVisiblePct": round(hands_vis, 2),
        "totalFramesAnalyzed": frames_count,
        "frames_analyzed": frames_count
    }

    # 3. Normalizar Métricas Acústicas
    clean_audio = {
        "palabrasTotales": int(audio_metrics.get("palabras_totales", audio_metrics.get("palabrasTotales", 0))),
        "duracionSegundos": float(audio_metrics.get("duracion_segundos", audio_metrics.get("duracionSegundos", 0.0))),
        "tiempoVozActivaSegundos": float(audio_metrics.get("tiempo_voz_activa_segundos", audio_metrics.get("tiempoVozActivaSegundos", 0.0))),
        "wpmGlobal": float(audio_metrics.get("wpm_global", audio_metrics.get("wpmGlobal", audio_metrics.get("wpm", 0.0)))),
        "ratioFonacion": float(audio_metrics.get("ratio_fonacion", audio_metrics.get("ratioFonacion", 0.0))),
        "pausasVacilacion": int(audio_metrics.get("pausas_vacilacion", audio_metrics.get("pausasVacilacion", 0))),
        "pausasProlongadas": int(audio_metrics.get("pausas_prolongadas", audio_metrics.get("pausasProlongadas", 0))),
        "densidadMuletillasPct": float(audio_metrics.get("densidad_muletillas_pct", audio_metrics.get("densidadMuletillasPct", 0.0))),
        "muletillasDetectadas": audio_metrics.get("muletillas_detectadas") or audio_metrics.get("muletillasDetectadas") or [],
        "scoreFluidez": float(audio_metrics.get("score_fluidez", audio_metrics.get("scoreFluidez", 0.0))),
        "scoreDiccion": float(audio_metrics.get("score_diccion", audio_metrics.get("scoreDiccion", 100.0)))
    }

    # 4. Normalizar Dimensiones del Juez
    raw_dims = judge_metrics.get("dimensiones", {})
    dim_map = {
        "pertinencia_respuesta": "pertinenciaRespuesta",
        "alineacion_mensaje_clave": "alineacionMensajeClave",
        "tecnicas_control": "tecnicasControl",
        "consistencia_institucional": "consistenciaInstitucional",
        "asertividad_hostilidad": "asertividadHostilidad",
        "capacidad_sintesis": "capacidadSintesis",
        "claridad_mensaje": "claridadMensaje"
    }
    clean_dims = {}
    for k, v in raw_dims.items():
        camel_k = dim_map.get(k, k)
        if isinstance(v, dict):
            clean_dims[camel_k] = {
                "nivel": v.get("nivel", v.get("score_1_5", 1)),
                "score": float(v.get("score_100", v.get("score", 0.0))),
                "criterio": v.get("criterio", v.get("justificacion", ""))
            }
        else:
            clean_dims[camel_k] = v

    clean_judge = {
        "puntajeGlobal100": float(judge_metrics.get("puntaje_global_100", judge_metrics.get("puntajeGlobal100", 0.0))),
        "dimensiones": clean_dims,
        "feedback": judge_metrics.get("feedback", {})
    }

    # 5. Narrativa y Señal Cruzada
    strengths = visum_narrative.get("desempeno_observado", {}).get("fortalezas", [])
    improvements = visum_narrative.get("desempeno_observado", {}).get("oportunidades_desarrollo", [])
    cross_signal = str(visum_narrative.get("observacion_senal_cruzada", ""))

    return {
        "sessionId": session_id,
        "session_id": session_id,
        "jobId": job_id or "",
        "job_id": job_id or "",
        "reportId": report_id or "",
        "report_id": report_id or "",
        "processedAt": processed_at,
        "processed_at": processed_at,
        "recordingUrl": recording_url,
        "overallScore": overall_score,
        "areaScores": [
            {"area": "expression", "value": area_scores.get("expression", 0)},
            {"area": "voice", "value": area_scores.get("voice", 0)},
            {"area": "coherence", "value": area_scores.get("coherence", 0)},
            {"area": "empathy", "value": area_scores.get("empathy", 0)}
        ],
        "puntuacion_global": {
            "score_general": overall_score,
            "areas": area_scores
        },
        "narrative": {
            "strengths": strengths,
            "improvements": improvements,
            "crossSignal": cross_signal,
            "visum": visum_clean
        },
        "metrics": {
            "vision": clean_vision,
            "audio": clean_audio,
            "judge": clean_judge,
            "turns_evaluated": len(segmented_turns or [])
        },
        "transcript": transcript
    }

