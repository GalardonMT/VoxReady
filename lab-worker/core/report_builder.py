import datetime
from typing import Dict, Any, Optional
from .analyzer import MultimodalVisionAnalyzer


def calculate_expression_area_score(vision_summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fase 3 (Playbook VISUM): Ponderación oficial para el área 'expression' (0 a 100):
    - Contacto visual: 40%
    - Estabilidad corporal y postura: 30%
    - Gesticulación (visibilidad y actividad de manos): 30%
    """
    return MultimodalVisionAnalyzer.calculate_expression_area_score(vision_summary)


class ReportBuilder:
    """
    Consolidador y fusionador matemático de métricas para sesiones de vocería VISUM.
    Integra los resultados de visión (manos, postura, balanceo y mirada),
    acústica/audio y evaluación del LLM Juez en un payload JSON unificado.
    """

    @staticmethod
    def build_consolidated_report(
        session_id: str,
        video_name: str,
        vision_result: Dict[str, Any],
        audio_result: Dict[str, Any],
        llm_result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Extracción y Fusión del Área de Expresión (VISUM)
        vision_summary = vision_result.get("visum_summary", {})
        if not vision_summary:
            vision_summary = {
                "eye_contact_pct": vision_result.get("contacto_visual_porcentaje", vision_result.get("metricas_ejes", {}).get("contacto_visual_porcentaje", 0.0)),
                "shoulder_stability_score": vision_result.get("shoulder_stability_score", vision_result.get("metricas_ejes", {}).get("estabilidad_balanceo_score", 100.0)),
                "body_sway_std": vision_result.get("body_sway_std", 0.0),
                "hands_visible_pct": vision_result.get("hands_visible_pct", 0.0),
                "hands_active_pct": vision_result.get("hands_active_pct", 0.0),
            }
        
        expression_calc = calculate_expression_area_score(vision_summary)
        score_visual = expression_calc["score"]

        # 2. Audio: Fluidez y dicción (sin pisos artificiales de 75)
        audio_metrics = audio_result.get("metrics", {}) if audio_result else {}
        if audio_metrics and "wpm" in audio_metrics:
            wpm = float(audio_metrics.get("wpm", 130.0))
            # Penalización por cadencia fuera de rango óptimo de media training (120 - 145)
            if wpm < 100.0:
                cadence_penalty = (100.0 - wpm) * 0.8
            elif wpm > 160.0:
                cadence_penalty = (wpm - 160.0) * 0.8
            else:
                cadence_penalty = 0.0

            fillers_pct = float(audio_metrics.get("densidad_muletillas_pct", 0.0))
            filler_penalty = min(25.0, fillers_pct * 5.0)

            score_fluidez = max(20.0, float(audio_metrics.get("score_fluidez", 80.0)) - cadence_penalty - filler_penalty)
            score_diccion = float(audio_metrics.get("score_diccion", 85.0))
            score_verbal = round(max(0.0, min(100.0, (score_fluidez * 0.60) + (score_diccion * 0.40))), 1)
        elif audio_metrics and ("score_fluidez" in audio_metrics or "score_diccion" in audio_metrics):
            score_fluidez = float(audio_metrics.get("score_fluidez", 50.0))
            score_diccion = float(audio_metrics.get("score_diccion", 50.0))
            score_verbal = round(max(0.0, min(100.0, (score_fluidez * 0.60) + (score_diccion * 0.40))), 1)
        else:
            score_verbal = 50.0

        # 3. LLM Juez Estratégico (Alineación y Control de Crisis)
        if llm_result and "puntaje_global_100" in llm_result:
            score_estrategico = float(llm_result["puntaje_global_100"])
            score_adherencia = float(llm_result.get("dimensiones", {}).get("alineacion_mensaje_clave", {}).get("score_100", score_estrategico))
            score_control = float(llm_result.get("dimensiones", {}).get("tecnicas_control", {}).get("score_100", score_estrategico))
            score_empatia = float(llm_result.get("dimensiones", {}).get("asertividad_hostilidad", {}).get("score_100", 50.0))
        else:
            score_estrategico = 50.0
            score_adherencia = 50.0
            score_control = 50.0
            score_empatia = 50.0

        # 4. Ponderación oficial de 4 Áreas VISUM:
        # Expresión 25% | Voz 25% | Contenido (Estrategia) 35% | Empatía 15%
        score_global = round(
            (score_visual * 0.25) +
            (score_verbal * 0.25) +
            (score_estrategico * 0.35) +
            (score_empatia * 0.15),
            1,
        )

        evaluacion_areas = {
            "expresion": {
                "score": score_visual,
                "contacto_visual_pct": expression_calc["metrics"].get("contacto_visual_pct", 0.0),
                "estabilidad_postural": expression_calc["metrics"].get("estabilidad_postural", 0.0),
                "manos_visibles_pct": expression_calc["metrics"].get("manos_visibles_pct", 0.0),
                "gesticulacion_activa_pct": expression_calc["metrics"].get("gesticulacion_activa_pct", 0.0),
                "balanceo_torso_std": expression_calc["metrics"].get("balanceo_torso_std", 0.0),
                "penalizacion_manos_ocultas": expression_calc["metrics"].get("penalizacion_manos_ocultas", 0.0)
            },
            "tono_voz": {
                "score": score_verbal,
                "wpm": float(audio_metrics.get("wpm", 130.0)) if audio_metrics else 130.0,
                "muletillas_count": len(audio_metrics.get("muletillas_detectadas", [])) if "muletillas_detectadas" in audio_metrics else int(audio_metrics.get("cantidad_muletillas", 0)),
            },
            "contenido": {
                "score": score_estrategico,
                "adherencia_mensajes": score_adherencia,
                "control_crisis": score_control
            },
            "empatia": {
                "score": score_empatia,
                "bridging_detectado": len(llm_result.get("dimensiones", {}).get("tecnicas_control", {}).get("tecnicas_detectadas", [])) > 0 if llm_result else False
            }
        }

        areas_evaluacion = {
            "expression": score_visual,
            "voice": score_verbal,
            "coherence": score_estrategico,
            "empathy": score_empatia,
        }

        return {
            "session_id": session_id,
            "video_name": video_name,
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
            "evaluacion_areas": evaluacion_areas,
            "evaluacion_expresion_visum": expression_calc,
            "evaluacion_llm_crisis": llm_result or {},
            "metricas_vision": vision_result,
            "metricas_audio_voz": audio_metrics,
        }

