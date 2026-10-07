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
