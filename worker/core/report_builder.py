import datetime
import hashlib
from typing import Dict, Any, Optional

try:
    from config.scoring_rules import (
        WEIGHT_EXPRESSION,
        WEIGHT_VOICE,
        WEIGHT_COHERENCE,
        WEIGHT_EMPATHY,
        VOICE_WEIGHT_WPM,
        VOICE_WEIGHT_FLUENCY,
        VOICE_WEIGHT_DICTION,
        RED_LINE_SCORE_CAP,
        EMPATHY_WEIGHT_VERBAL,
        EMPATHY_WEIGHT_NONVERBAL,
        DICTION_FALLBACK_SCORE,
        DynamicRubricConfig,
    )
except (ImportError, ValueError):
    try:
        from core.scoring_rules import (
            WEIGHT_EXPRESSION,
            WEIGHT_VOICE,
            WEIGHT_COHERENCE,
            WEIGHT_EMPATHY,
            VOICE_WEIGHT_WPM,
            VOICE_WEIGHT_FLUENCY,
            VOICE_WEIGHT_DICTION,
            RED_LINE_SCORE_CAP,
            EMPATHY_WEIGHT_VERBAL,
            EMPATHY_WEIGHT_NONVERBAL,
            DICTION_FALLBACK_SCORE,
            DynamicRubricConfig,
        )
    except (ImportError, ValueError):
        from worker.config.scoring_rules import (
            WEIGHT_EXPRESSION,
            WEIGHT_VOICE,
            WEIGHT_COHERENCE,
            WEIGHT_EMPATHY,
            VOICE_WEIGHT_WPM,
            VOICE_WEIGHT_FLUENCY,
            VOICE_WEIGHT_DICTION,
            RED_LINE_SCORE_CAP,
            EMPATHY_WEIGHT_VERBAL,
            EMPATHY_WEIGHT_NONVERBAL,
            DICTION_FALLBACK_SCORE,
            DynamicRubricConfig,
        )



def compute_empathy_score(non_verbal_score: float, victim_level: int) -> float:
    """Calcula el área de empatía combinando el reconocimiento del afectado (verbal 60%)
    con la compostura y contacto visual no verbal (40%).
    """
    safe_level = max(1, min(5, int(round(float(victim_level or 3)))))
    verbal_score = ((safe_level - 1) / 4.0) * 100.0
    final_empathy = (non_verbal_score * EMPATHY_WEIGHT_NONVERBAL) + (verbal_score * EMPATHY_WEIGHT_VERBAL)
    return round(final_empathy, 1)


def evaluate_metric_bands(
    metrics_summary: Dict[str, Any],
    rubric_cfg: Optional[DynamicRubricConfig] = None
) -> Dict[str, str]:
    """
    Clasifica las métricas clave en 'optimal', 'warning' o 'critical'
    según los umbrales configurados en DynamicRubricConfig.
    """
    cfg = rubric_cfg or DynamicRubricConfig()
    bands = {}

    # voice.wpm
    wpm = metrics_summary.get("wpm") or metrics_summary.get("wpm_global") or metrics_summary.get("wpmGlobal")
    if wpm is not None:
        th = cfg.get_metric("voice.wpm")
        w_val = float(wpm)
        if float(th.get("optimalLow", 120)) <= w_val <= float(th.get("optimalHigh", 150)):
            bands["voice.wpm"] = "optimal"
        elif float(th.get("warningLow", 100)) <= w_val <= float(th.get("warningHigh", 170)):
            bands["voice.wpm"] = "warning"
        else:
            bands["voice.wpm"] = "critical"

    # voice.filler_density
    filler = metrics_summary.get("densidad_muletillas_pct") or metrics_summary.get("densidadMuletillasPct") or metrics_summary.get("fillerWordsDensityPct")
    if filler is not None:
        th = cfg.get_metric("voice.filler_density")
        f_val = float(filler)
        if f_val <= float(th.get("optimalMax", 1.5)):
            bands["voice.filler_density"] = "optimal"
        elif f_val <= float(th.get("warningMax", 3.0)):
            bands["voice.filler_density"] = "warning"
        else:
            bands["voice.filler_density"] = "critical"

    # voice.phonation_ratio
    pr = metrics_summary.get("ratio_fonacion") or metrics_summary.get("ratioFonacion")
    if pr is not None:
        th = cfg.get_metric("voice.phonation_ratio")
        pr_val = float(pr)
        if pr_val <= 1.0:
            pr_val *= 100.0
        if float(th.get("optimalLow", 60)) <= pr_val <= float(th.get("optimalHigh", 85)):
            bands["voice.phonation_ratio"] = "optimal"
        elif pr_val >= float(th.get("criticalBelow", 45)):
            bands["voice.phonation_ratio"] = "warning"
        else:
            bands["voice.phonation_ratio"] = "critical"

    # voice.asr_confidence
    asr = metrics_summary.get("score_diccion") or metrics_summary.get("scoreDiccion")
    if asr is not None:
        th = cfg.get_metric("voice.asr_confidence")
        a_val = float(asr)
        if a_val >= float(th.get("optimalLow", 85)):
            bands["voice.asr_confidence"] = "optimal"
        elif a_val >= float(th.get("warningLow", 70)):
            bands["voice.asr_confidence"] = "warning"
        else:
            bands["voice.asr_confidence"] = "critical"

    # vision.eye_contact
    eye = metrics_summary.get("eye_contact_pct") or metrics_summary.get("eyeContactPct") or metrics_summary.get("contacto_visual_pct")
    if eye is not None:
        th = cfg.get_metric("vision.eye_contact")
        e_val = float(eye)
        if e_val >= float(th.get("optimalLow", 75)):
            bands["vision.eye_contact"] = "optimal"
        elif e_val >= float(th.get("warningLow", 50)):
            bands["vision.eye_contact"] = "warning"
        else:
            bands["vision.eye_contact"] = "critical"

    # vision.posture
    posture = metrics_summary.get("shoulder_stability_score") or metrics_summary.get("shoulderStabilityScore")
    if posture is not None:
        th = cfg.get_metric("vision.posture")
        p_val = float(posture)
        if p_val >= float(th.get("optimalLow", 75)):
            bands["vision.posture"] = "optimal"
        elif p_val >= float(th.get("warningLow", 50)):
            bands["vision.posture"] = "warning"
        else:
            bands["vision.posture"] = "critical"

    # vision.sway_tolerance
    sway = metrics_summary.get("body_sway_std") or metrics_summary.get("bodySwayStd")
    if sway is not None:
        th = cfg.get_metric("vision.sway_tolerance")
        s_val = float(sway)
        if s_val <= float(th.get("optimalMax", 0.015)):
            bands["vision.sway_tolerance"] = "optimal"
        elif s_val <= float(th.get("warningMax", 0.035)):
            bands["vision.sway_tolerance"] = "warning"
        else:
            bands["vision.sway_tolerance"] = "critical"

    # empathy.victim_recog
    rec = metrics_summary.get("victim_level") or metrics_summary.get("victimLevel")
    if rec is not None:
        th = cfg.get_metric("empathy.victim_recog")
        r_val = float(rec)
        if r_val >= float(th.get("optimalLevel", 4.0)):
            bands["empathy.victim_recog"] = "optimal"
        elif r_val >= float(th.get("warningLevel", 3.0)):
            bands["empathy.victim_recog"] = "warning"
        else:
            bands["empathy.victim_recog"] = "critical"

    return bands


def compute_governance_metrics(
    session_id: str,
    overall_score: float,
    area_scores: Dict[str, float],
    vision_metrics: Dict[str, Any],
    audio_metrics: Dict[str, Any],
    rubric_cfg: Optional[DynamicRubricConfig] = None
) -> Dict[str, Any]:
    """
    Calcula las métricas de Gobernanza de Nivel 2 y evalúa enrutamiento a auditoría humana (dbo.labeling_case).
    """
    cfg = rubric_cfg or DynamicRubricConfig()

    # 1. Tasa de fotogramas válidos de visión (0 - 100%)
    total_frames = int(
        vision_metrics.get("total_frames_analyzed")
        or vision_metrics.get("totalFramesAnalyzed")
        or vision_metrics.get("frames_analyzed")
        or vision_metrics.get("total_frames_analizados")
        or 0
    )
    valid_frames = int(
        vision_metrics.get("frames_validos")
        if vision_metrics.get("frames_validos") is not None
        else total_frames
    )
    vision_validity_pct = (valid_frames / max(1, total_frames)) * 100.0 if total_frames > 0 else 70.0

    # 2. Certeza fonética ASR Parakeet (0 - 100%)
    asr_confidence_pct = float(
        audio_metrics.get("score_diccion")
        if audio_metrics.get("score_diccion") is not None
        else (audio_metrics.get("scoreDiccion") if audio_metrics.get("scoreDiccion") is not None else 70.0)
    )

    # 3. Confianza técnica del pipeline (Promedio directo Vision Validity + Score Dicción)
    pipeline_confidence = round((vision_validity_pct + asr_confidence_pct) / 2.0, 1)

    # 4. Disparidad inter-canal (máximo menos mínimo de las 4 áreas)
    vals = [float(v) for v in area_scores.values()] if area_scores else [0.0]
    disparity_delta = round(max(vals) - min(vals), 1)

    # 5. Lectura de umbrales de Gobernanza desde DynamicRubricConfig
    conf_limits = cfg.get_metric("gov.confidence_min")
    conf_warning_low = float(conf_limits.get("warningLow", 70.0))
    conf_optimal_low = float(conf_limits.get("optimalLow", 85.0))

    half_width = float(cfg.get_metric("gov.borderline_delta").get("halfWidth", 2.0))
    borderline_min = 50.0 - half_width
    borderline_max = 50.0 + half_width

    disp_limits = cfg.get_metric("gov.disparity_delta")
    disparity_normal_below = float(disp_limits.get("normalBelow", 35.0))
    disparity_audit_at = float(disp_limits.get("auditAt", 50.0))

    random_rate_pct = float(cfg.get_metric("gov.random_sample").get("rate", 10.0))

    # 6. Evaluación de triggers hacia dbo.labeling_case
    detailed_triggers = []
    if pipeline_confidence < conf_warning_low:
        detailed_triggers.append("low_confidence")
    if borderline_min <= overall_score <= borderline_max:
        detailed_triggers.append("borderline_score")
    if disparity_delta >= disparity_audit_at:
        detailed_triggers.append("inter_channel_disparity")

    # Mapeo al motivo SQL oficial ('low_confidence', 'borderline', 'random')
    labeling_reason = None
    if "low_confidence" in detailed_triggers:
        labeling_reason = "low_confidence"
    elif "borderline_score" in detailed_triggers or "inter_channel_disparity" in detailed_triggers:
        labeling_reason = "borderline"
    elif random_rate_pct > 0:
        digest = int(hashlib.md5(str(session_id).encode("utf-8")).hexdigest()[:8], 16)
        if (digest % 1000) / 10.0 < random_rate_pct:
            detailed_triggers.append("random_sample")
            labeling_reason = "random"

    confidence_band = (
        "optimal" if pipeline_confidence >= conf_optimal_low
        else ("warning" if pipeline_confidence >= conf_warning_low else "critical")
    )
    disparity_band = (
        "optimal" if disparity_delta < disparity_normal_below
        else ("warning" if disparity_delta < disparity_audit_at else "critical")
    )

    return {
        "pipeline_confidence_score": pipeline_confidence,
        "vision_validity_pct": round(vision_validity_pct, 1),
        "asr_confidence_pct": round(asr_confidence_pct, 1),
        "inter_channel_disparity_delta": disparity_delta,
        "confidence_band": confidence_band,
        "disparity_band": disparity_band,
        "requires_human_review": labeling_reason is not None,
        "labeling_reason": labeling_reason,
        "detailed_triggers": detailed_triggers,
        "rubric_version_id": cfg.rubric_version_id,
        "rubric_version_code": cfg.version_code,
        # Claves camelCase para consumo directo en Frontend
        "pipelineConfidenceScore": pipeline_confidence,
        "visionValidityPct": round(vision_validity_pct, 1),
        "asrConfidencePct": round(asr_confidence_pct, 1),
        "interChannelDisparityDelta": disparity_delta,
        "confidenceBand": confidence_band,
        "disparityBand": disparity_band,
        "requiresHumanReview": labeling_reason is not None,
        "labelingReason": labeling_reason,
        "detailedTriggers": detailed_triggers,
        "rubricVersionId": cfg.rubric_version_id,
        "rubricVersionCode": cfg.version_code,
    }



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
        rubric_cfg: Optional[DynamicRubricConfig] = None,
    ) -> Dict[str, Any]:
        cfg = rubric_cfg or DynamicRubricConfig()
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

        # Audio: WPM, fluidez neta y dicción real
        audio_metrics = audio_result.get("metrics", {})
        score_wpm = float(audio_metrics.get("score_wpm", 80.0))
        score_fluidez = float(audio_metrics.get("score_fluidez", 75.0))
        score_diccion = float(audio_metrics.get("score_diccion", DICTION_FALLBACK_SCORE))
        score_verbal = round(max(0.0, min(100.0,
            (score_wpm * VOICE_WEIGHT_WPM) +
            (score_fluidez * VOICE_WEIGHT_FLUENCY) +
            (score_diccion * VOICE_WEIGHT_DICTION)
        )), 1)

        # LLM: Juez Visum o apego a mensajes
        infraccion_linea_roja = bool(llm_result.get("infraccion_linea_roja", False))
        evidencia_linea_roja = llm_result.get("evidencia_linea_roja")

        if "puntaje_global_100" in llm_result:
            score_estrategico = float(llm_result["puntaje_global_100"])
            score_adherencia = float(llm_result.get("dimensiones", {}).get("alineacion_mensaje_clave", {}).get("score_100", score_estrategico))
            score_control = float(llm_result.get("dimensiones", {}).get("tecnicas_control", {}).get("score_100", score_estrategico))
        else:
            score_adherencia = float(llm_result.get("key_message_adherence_score", 70.0))
            score_control = float(llm_result.get("crisis_control_score", 70.0))
            score_estrategico = round(max(0.0, min(100.0, (score_adherencia * 0.50) + (score_control * 0.50))), 1)

        # Salvaguarda determinista: Si se vulneró una línea roja, Coherencia no puede superar cfg.red_line_cap
        if infraccion_linea_roja:
            score_estrategico = min(score_estrategico, cfg.red_line_cap)

        # Empatía balanceada: 60% verbal (reconocimiento del afectado) + 40% no verbal (contacto visual y postura)
        rec_afectados = llm_result.get("reconocimiento_afectados") or {}
        victim_level = rec_afectados.get("nivel", 3) if isinstance(rec_afectados, dict) else 3
        score_empatia = compute_empathy_score(score_visual, victim_level)

        # 2. Score Global Compuesto de la Sesión (4 Ejes Oficiales)
        w_expr = cfg.area_weights.get("expression", WEIGHT_EXPRESSION)
        w_voice = cfg.area_weights.get("voice", WEIGHT_VOICE)
        w_coherence = cfg.area_weights.get("coherence", WEIGHT_COHERENCE)
        w_empathy = cfg.area_weights.get("empathy", WEIGHT_EMPATHY)

        score_global = round(
            (score_visual * w_expr) +
            (score_verbal * w_voice) +
            (score_estrategico * w_coherence) +
            (score_empatia * w_empathy),
            1,
        )

        areas_evaluacion = {
            "expression": score_visual,
            "voice": score_verbal,
            "coherence": score_estrategico,
            "empathy": score_empatia,
        }

        # 3. Gobernanza Nivel 2 y Auditoría
        gov_metrics = compute_governance_metrics(
            session_id=session_id,
            overall_score=score_global,
            area_scores=areas_evaluacion,
            vision_metrics=vision_summary,
            audio_metrics=audio_metrics,
            rubric_cfg=cfg,
        )

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
                "infraccion_linea_roja": infraccion_linea_roja,
                "evidencia_linea_roja": evidencia_linea_roja,
                "reconocimiento_afectados": rec_afectados,
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
                "score_wpm": score_wpm,
                "score_fluidez": score_fluidez,
                "score_diccion": score_diccion,
            },
            "transcripcion": {
                "texto_completo": audio_result.get("transcription", ""),
                "palabras_con_marcas_tiempo": audio_result.get("words", []),
            },
            "governance": gov_metrics,
        }

        return report


def sanitize_report_json(
    session_id: str,
    job_id: Optional[str] = None,
    report_id: Optional[str] = None,
    processed_at: Optional[str] = None,
    recording_url: Optional[str] = None,
    overall_score: Optional[Any] = None,
    area_scores: Optional[Dict[str, Any]] = None,
    visum_narrative: Optional[Dict[str, Any]] = None,
    vision_metrics: Optional[Dict[str, Any]] = None,
    audio_metrics: Optional[Dict[str, Any]] = None,
    judge_metrics: Optional[Dict[str, Any]] = None,
    transcript: Optional[str] = None,
    segmented_turns: Optional[list] = None,
    governance: Optional[Dict[str, Any]] = None,
    consolidated_report: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Sanea y normaliza el reporte consolidado de acuerdo con la Especificación Técnica (Sección 1):
    1. Elimina informe_ejecutivo_visum de la raíz, preservando únicamente narrative.visum.
    2. Unifica las métricas de visión a estándar técnico en camelCase sin duplicidades en español.
    3. Normaliza métricas acústicas y dimensiones pedagógicas del LLM Juez.
    """
    cr = consolidated_report or {}
    p_global = cr.get("puntuacion_global", {})
    if area_scores is None:
        area_scores = p_global.get("areas", {})
    if overall_score is None:
        overall_score = p_global.get("score_general", 0)
    if recording_url is None:
        recording_url = cr.get("recording_url", "")
    if processed_at is None:
        processed_at = cr.get("processed_at", cr.get("completed_at", ""))
    if vision_metrics is None:
        vision_metrics = cr.get("metricas_vision", {})
    if audio_metrics is None:
        audio_metrics = cr.get("metricas_audio_voz", {})
    if judge_metrics is None:
        judge_metrics = cr.get("evaluacion_llm_crisis", {})
    if visum_narrative is None:
        visum_narrative = (
            cr.get("evaluacion_llm_crisis", {}).get("feedback_pedagogico")
            or cr.get("narrative", {}).get("visum")
            or {}
        )
    if transcript is None:
        transcript = cr.get("transcripcion", {}).get("texto_completo", "")
    if governance is None:
        governance = cr.get("governance", kwargs.get("governance", {}))

    # 1. Normalizar Visum
    visum_narrative = visum_narrative or {}
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
        "scoreWpm": float(audio_metrics.get("score_wpm", audio_metrics.get("scoreWpm", 80.0))),
        "scoreFluidez": float(audio_metrics.get("score_fluidez", audio_metrics.get("scoreFluidez", 0.0))),
        "scoreDiccion": float(audio_metrics.get("score_diccion", audio_metrics.get("scoreDiccion", DICTION_FALLBACK_SCORE)))
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

    infraccion_lr = bool(judge_metrics.get("infraccion_linea_roja", judge_metrics.get("infraccionLineaRoja", False)))
    evidencia_lr = judge_metrics.get("evidencia_linea_roja") or judge_metrics.get("evidenciaLineaRoja")
    rec_afectados_raw = judge_metrics.get("reconocimiento_afectados") or judge_metrics.get("reconocimientoAfectados") or {}
    
    clean_judge = {
        "puntajeGlobal100": float(judge_metrics.get("puntaje_global_100", judge_metrics.get("puntajeGlobal100", 0.0))),
        "dimensiones": clean_dims,
        "feedback": judge_metrics.get("feedback", {}),
        "infraccionLineaRoja": infraccion_lr,
        "evidenciaLineaRoja": evidencia_lr,
        "reconocimientoAfectados": {
            "nivel": rec_afectados_raw.get("nivel", 3) if isinstance(rec_afectados_raw, dict) else 3,
            "score": float(rec_afectados_raw.get("score_100", rec_afectados_raw.get("score", 50.0))) if isinstance(rec_afectados_raw, dict) else 50.0,
            "criterio": rec_afectados_raw.get("criterio", "Mención neutra de afectados.") if isinstance(rec_afectados_raw, dict) else "Mención neutra de afectados."
        }
    }

    # 5. Narrativa y Señal Cruzada
    strengths = visum_narrative.get("desempeno_observado", {}).get("fortalezas", [])
    improvements = list(visum_narrative.get("desempeno_observado", {}).get("oportunidades_desarrollo", []))
    cross_signal = str(visum_narrative.get("observacion_senal_cruzada", ""))

    # Si hubo infracción de línea roja, inyectar alerta prioritaria en narrative improvements
    if infraccion_lr:
        alerta_lr = f"ALERTA CRÍTICA: Vulneraste una línea roja del escenario ({evidencia_lr or 'Infracción de política institucional'})."
        if alerta_lr not in improvements:
            improvements.insert(0, alerta_lr)

    score_exp = float(area_scores.get("expression", area_scores.get("expresion", 0.0)))
    score_v = float(area_scores.get("voice", area_scores.get("voz", 0.0)))
    score_c = float(area_scores.get("coherence", area_scores.get("coherencia", area_scores.get("contenido", 0.0))))
    score_e = float(area_scores.get("empathy", area_scores.get("empatia", 0.0)))
    score_glob = float(overall_score if overall_score is not None else 0.0)

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
        "overallScore": score_glob,
        "scoreGlobal": score_glob,
        "score_global": score_glob,
        "scoreExpresion": score_exp,
        "score_expresion": score_exp,
        "scoreVoz": score_v,
        "score_voz": score_v,
        "scoreCoherencia": score_c,
        "score_coherencia": score_c,
        "scoreContenido": score_c,
        "score_contenido": score_c,
        "scoreEmpatia": score_e,
        "score_empatia": score_e,
        "areas": {
            "expresion": score_exp,
            "voz": score_v,
            "coherencia": score_c,
            "contenido": score_c,
            "empatia": score_e,
        },
        "areaScores": [
            {"area": "expression", "value": area_scores.get("expression", score_exp)},
            {"area": "voice", "value": area_scores.get("voice", score_v)},
            {"area": "coherence", "value": area_scores.get("coherence", score_c)},
            {"area": "empathy", "value": area_scores.get("empathy", score_e)}
        ],
        "puntuacion_global": {
            "score_general": score_glob,
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
        "transcript": transcript,
        "governance": governance or {}
    }

