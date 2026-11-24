"""Unit tests for worker turn-based aggregation, vision batching, judge dialogue, and labeling contracts."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

WORKER_DIR = Path(__file__).resolve().parents[1]
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from core.audio_analyzer import aggregate_turn_audio_results
from core.llm_judge import LLMJudgeService, format_interview_dialogue
from core.pipeline_orchestrator import probe_media_duration, remux_webm_for_seeking, split_media
from core.report_builder import sanitize_report_json
from core.schemas import (
    DimensionScore,
    EvaluacionDimensiones,
    EvaluacionLLMResponse,
    FeedbackPedagogico,
    MensajeClaveScore,
    TecnicasControlScore,
)
from core.vision_client import VisionClient
from services import labeling_runtime


def _metric_catalog():
    category_by_prefix = {
        "voice": "voice",
        "vision": "vision",
        "content": "content",
        "empathy": "empathy",
        "gov": "governance",
    }
    units = {
        "voice.wpm": "WPM",
        "voice.filler_density": "%",
        "voice.prolonged_pause": "pausas",
        "voice.hesitation_pause": "pausas",
        "voice.phonation_ratio": "%",
        "voice.asr_confidence": "%",
        "vision.eye_contact": "%",
        "vision.posture": "%",
        "vision.sway_tolerance": "std",
        "content.red_line_cap": "pts",
        "empathy.victim_recog": "nivel",
        "gov.confidence_min": "%",
        "gov.borderline_delta": "pts",
        "gov.disparity_delta": "pts",
        "gov.random_sample": "%",
        "gov.agreement_target": "ratio",
    }
    thresholds = {
        "gov.borderline_delta": {"halfWidth": 2},
        "gov.disparity_delta": {"auditAt": 50},
    }
    return [
        {
            "metricKey": key,
            "categoryKey": category_by_prefix[key.split(".")[0]],
            "label": key,
            "unit": units[key],
            "publishedThresholds": thresholds.get(key, {}),
        }
        for key in sorted(labeling_runtime.EXPECTED_METRIC_KEYS)
    ]


def test_turn_audio_aggregation_intra_turn_pauses_and_last_word_trim():
    # Turn 1: raw 15s, spoke until 10.0s (5s button delay!), 1 intra-turn prolonged pause (2.0s)
    # Turn 2: starts 25s later (interviewer spoke between turns!) -> MUST NOT count as prolonged pause!
    turns = [
        {
            "turn_index": 1,
            "base_sequence_no": 1,
            "turn_kind": "base",
            "question_text": "¿Qué ocurrió?",
            "transcript": "prioridad seguridad personas ahora",
            "start_offset_ms": 2000,
            "end_offset_ms": 17000,
            "audio_duration_sec": 15.0,
            "speech_time_sec": 8.0,
            "acoustic_pauses": [
                {"inicio_segundo": 10.5, "duracion_segundos": 4.5},  # trailing button delay -> MUST be excluded
            ],
            "words": [
                {"word": "prioridad", "start": 0.2, "end": 1.0, "confidence": 0.90},
                {"word": "seguridad", "start": 3.0, "end": 4.0, "confidence": 0.92},  # gap 2.0s -> 1 prolonged pause
                {"word": "personas", "start": 4.8, "end": 6.0, "confidence": 0.94},   # gap 0.8s -> 1 hesitation pause
                {"word": "ahora", "start": 6.2, "end": 10.0, "confidence": 0.96},
            ],
        },
        {
            "turn_index": 2,
            "base_sequence_no": 1,
            "turn_kind": "follow_up",
            "question_text": "¿Cuándo restablecen el servicio?",
            "transcript": "equipo técnico trabajando",
            "start_offset_ms": 42000,  # 25s after turn 1 ended -> MUST NOT create inter-turn pause
            "end_offset_ms": 50000,
            "audio_duration_sec": 8.0,
            "speech_time_sec": 4.5,
            "acoustic_pauses": [],
            "words": [
                {"word": "equipo", "start": 0.1, "end": 1.5, "confidence": 0.88},
                {"word": "técnico", "start": 1.7, "end": 3.0, "confidence": 0.90},
                {"word": "trabajando", "start": 3.2, "end": 5.0, "confidence": 0.92},
            ],
        },
    ]

    res = aggregate_turn_audio_results(turns)
    metrics = res["metrics"]
    ac = res["acoustic_analysis"]

    # Effective duration trimmed to last_word.end: 10.0s + 5.0s = 15.0s (NOT 23.0s)
    assert ac["total_duration_sec"] == pytest.approx(15.0, abs=0.01)
    assert ac["speech_time_sec"] == pytest.approx(12.5, abs=0.01)
    assert metrics["ratio_fonacion"] == pytest.approx(12.5 / 15.0, abs=0.001)
    assert 0.0 <= metrics["ratio_fonacion"] <= 1.0

    # Strictly 1 prolonged pause (intra-turn 1) and 1 hesitation pause; ZERO inter-turn pauses
    assert metrics["pausas_prolongadas"] == 1
    assert metrics["pausas_vacilacion"] == 1
    assert metrics["palabras_totales"] == 7
    assert metrics["wpm_global"] == pytest.approx(7 / (15.0 / 60.0), abs=0.1)

    # All words preserved with timeline offsets and valid confidence for labeling_runtime
    assert len(res["words"]) == 7
    assert res["words"][0]["start"] == pytest.approx(2.2, abs=0.01)
    assert res["words"][4]["start"] == pytest.approx(42.1, abs=0.01)

    # End-to-end compatibility check with labeling_runtime.build_labeling_snapshot (16 metrics)
    voice_pipeline_payload = dict(metrics)
    voice_pipeline_payload["words"] = res["words"]

    vision_batches = _build_exact_vision_batches()
    consolidated_vision = VisionClient.consolidate_batch_responses(vision_batches)

    snapshot = labeling_runtime.build_labeling_snapshot(
        report={
            "clientId": "c1",
            "sessionId": "s1",
            "reportId": "r1",
            "analysisJobId": "j1",
            "rubricVersionId": "rv1",
            "overallScore": 84,
        },
        areas=[
            {"areaId": "a1", "areaKey": "expression", "aiValue": 82},
            {"areaId": "a2", "areaKey": "voice", "aiValue": 84},
            {"areaId": "a3", "areaKey": "coherence", "aiValue": 86},
            {"areaId": "a4", "areaKey": "empathy", "aiValue": 83},
        ],
        pipeline_results={
            "voice": voice_pipeline_payload,
            "vision": consolidated_vision,
            "content_judge": {"puntaje_global_100": 86},
            "fusion": {"reportId": "r1"},
        },
        metric_catalog=_metric_catalog(),
        evidence={
            "sealedPath": "labeling-evidence/s1/j1/abc.webm",
            "versionId": None,
            "sha256": "a" * 64,
            "etag": '"etag"',
            "contentType": "video/webm",
            "durationSeconds": 65.0,
        },
    )
    assert snapshot["sourceStatus"] == "complete"
    metric_map = {m["metricKey"]: m for m in snapshot["snapshot"]["metrics"]}
    assert metric_map["voice.phonation_ratio"]["availability"] == "available"
    assert metric_map["voice.asr_confidence"]["availability"] == "available"
    assert metric_map["vision.sway_tolerance"]["availability"] == "available"


def _build_exact_vision_batches():
    b1_details = [
        {
            "valid": True,
            "eye_contact": True,
            "pose_detected": True,
            "shoulder_slope": 0.01,
            "torso_center_x": 0.48 + (i * 0.002),
            "hands_visible": True,
            "hands_active": i % 2 == 0,
        }
        for i in range(10)
    ]
    b2_details = [
        {
            "valid": True,
            "eye_contact": False,
            "pose_detected": True,
            "shoulder_slope": 0.02,
            "torso_center_x": 0.52 + (i * 0.001),
            "hands_visible": False,
            "hands_active": False,
        }
        for i in range(10)
    ]
    return [
        {"summary": {"total_frames_analyzed": 10}, "frame_details": b1_details},
        {"summary": {"total_frames_analyzed": 10}, "frame_details": b2_details},
    ]


def test_vision_batch_consolidation_exact_and_fallback_and_chunking():
    batches = _build_exact_vision_batches()
    consolidated = VisionClient.consolidate_batch_responses(batches)
    assert consolidated is not None
    all_details = batches[0]["frame_details"] + batches[1]["frame_details"]
    expected_sway = round(float(np.std([f["torso_center_x"] for f in all_details])), 4)
    assert consolidated["summary"]["total_frames_analyzed"] == 20
    assert consolidated["summary"]["eye_contact_pct"] == 50.0
    assert consolidated["summary"]["hands_visible_pct"] == 50.0
    assert consolidated["summary"]["hands_active_pct"] == 25.0
    assert consolidated["summary"]["body_sway_std"] == expected_sway

    # Fallback consolidation (without frame_details) -> weighted average + pooled RMS sway
    fallback_batches = [
        {
            "summary": {
                "eye_contact_pct": 80.0,
                "hands_visible_pct": 60.0,
                "hands_active_pct": 40.0,
                "shoulder_stability_score": 90.0,
                "body_sway_std": 0.010,
                "total_frames_analyzed": 60,
            }
        },
        {
            "summary": {
                "eye_contact_pct": 50.0,
                "hands_visible_pct": 30.0,
                "hands_active_pct": 10.0,
                "shoulder_stability_score": 80.0,
                "body_sway_std": 0.020,
                "total_frames_analyzed": 30,
            }
        },
    ]
    fb = VisionClient.consolidate_batch_responses(fallback_batches)
    assert fb["summary"]["total_frames_analyzed"] == 90
    assert fb["summary"]["eye_contact_pct"] == 70.0
    expected_rms = round(math.sqrt((60 * (0.010 ** 2) + 30 * (0.020 ** 2)) / 90), 4)
    assert fb["summary"]["body_sway_std"] == expected_rms

    # Chunking verification: 150 frames with batch_size=60 -> 3 chunks (60, 60, 30)
    vc = VisionClient(base_url="http://fake-vision", batch_size=60)
    seen_chunk_sizes = []

    def fake_single(chunk):
        seen_chunk_sizes.append(len(chunk))
        return {
            "summary": {
                "eye_contact_pct": 75.0,
                "hands_visible_pct": 50.0,
                "hands_active_pct": 25.0,
                "shoulder_stability_score": 88.0,
                "body_sway_std": 0.012,
                "total_frames_analyzed": len(chunk),
            },
            "frame_details": [],
        }

    with patch.object(vc, "_analyze_single_batch", side_effect=fake_single):
        out = vc.analyze_batch([f"f_{i}.jpg" for i in range(150)])
    assert seen_chunk_sizes == [60, 60, 30]
    assert out["summary"]["total_frames_analyzed"] == 150


def test_split_media_adaptive_fps_and_max_frames(tmp_path, monkeypatch):
    cmds = []

    def fake_run(cmd, **_kwargs):
        cmds.append(cmd)
        # Create dummy frame files matching the frames_dir pattern (> 60 to test uniform subsampling)
        if "-vf" in cmd:
            out_pattern = Path(cmd[-1])
            out_dir = out_pattern.parent
            for i in range(1, 85):
                (out_dir / f"frame_{i:05d}.jpg").write_bytes(b"jpg")
        res = MagicMock()
        res.returncode = 0
        res.stderr = ""
        return res

    monkeypatch.setattr("core.pipeline_orchestrator.subprocess.run", fake_run)
    monkeypatch.setenv("VISION_MAX_FRAMES", "60")

    # <= 300s -> 2 FPS
    _, frames_short = split_media("in.webm", str(tmp_path / "short"), extract_audio=False, video_duration_sec=180.0)
    assert "fps=2" in cmds[-1]
    assert len(frames_short) == 60

    # > 300s -> 1 FPS
    _, frames_long = split_media("in.webm", str(tmp_path / "long"), extract_audio=False, video_duration_sec=480.0)
    assert "fps=1" in cmds[-1]
    assert len(frames_long) == 60


def test_llm_judge_structured_dialogue_and_report_builder():
    turns = [
        {
            "turnIndex": 1,
            "baseSequenceNo": 1,
            "turnKind": "base",
            "questionText": "¿Por qué falló el sistema?",
            "transcript": "Estamos investigando las causas con prioridad en los clientes.",
        },
        {
            "turnIndex": 2,
            "baseSequenceNo": 1,
            "turnKind": "follow_up",
            "questionText": "¿Descarta entonces negligencia interna?",
            "transcript": "No vamos a especular hasta concluir el peritaje técnico independiente.",
        },
    ]

    formatted = format_interview_dialogue(turns)
    assert "[Turno 1 · Pregunta Base #1]" in formatted
    assert "[Turno 2 · Contrapregunta IA sobre Pregunta Base #1]" in formatted

    judge = LLMJudgeService(api_key="fake-key", model="gemini-3.5-flash-lite")
    mock_eval = EvaluacionLLMResponse(
        evaluacion_dimensiones=EvaluacionDimensiones(
            pertinencia_respuesta=DimensionScore(nivel=4, criterio="Respondió bien"),
            tecnicas_control=TecnicasControlScore(nivel=4, criterio="Buen bridging"),
            alineacion_mensaje_clave=MensajeClaveScore(nivel=5, criterio="Alineado"),
            capacidad_sintesis=DimensionScore(nivel=4, criterio="Claro"),
            claridad_mensaje=DimensionScore(nivel=4, criterio="Directo"),
            consistencia_institucional=DimensionScore(nivel=5, criterio="Respetó líneas rojas"),
            asertividad_hostilidad=DimensionScore(nivel=4, criterio="Firme ante contrapregunta"),
        ),
        feedback_pedagogico=FeedbackPedagogico(
            fortaleza_principal="Sostuvo la disciplina ante la contrapregunta",
            brecha_critica="Dar plazos concretos",
            recomendacion_accionable="Cerrar con compromiso verificable",
        ),
        infraccion_linea_roja=False,
        evidencia_linea_roja=None,
        reconocimiento_afectados=DimensionScore(nivel=4, criterio="Priorizó clientes"),
    )
    mock_completion = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_eval
    mock_completion.choices = [mock_choice]

    with patch.object(judge.client.beta.chat.completions, "parse", return_value=mock_completion) as mock_parse:
        reporte = judge.evaluate_response(
            pregunta_periodista=turns[0]["questionText"],
            mensajes_clave=["Prioridad en clientes"],
            contexto_crisis="Falla técnica",
            transcripcion_vocero=formatted,
            lineas_rojas=["No especular sobre negligencia"],
            interview_turns=turns,
        )
        assert reporte.puntaje_global_100 >= 75.0
        sent_messages = mock_parse.call_args[1]["messages"]
        assert "DIÁLOGO COMPLETO DE LA ENTREVISTA POR TURNOS" in sent_messages[1]["content"]
        assert "Contrapregunta IA" in sent_messages[1]["content"]

    cleaned = sanitize_report_json(
        session_id="s-1",
        overall_score=85,
        area_scores={"expression": 80, "voice": 85, "coherence": 88, "empathy": 86},
        transcript=formatted,
        dialogue_turns=turns,
        master_duration_seconds=142.5,
    )
    assert cleaned["dialogueTurns"] == turns
    assert cleaned["durationSeconds"] == 142.5
    assert cleaned["metrics"]["turns_evaluated"] == 2


def test_probe_media_duration_rejects_subsecond_header_and_uses_ffmpeg_fallback(monkeypatch):
    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        res = MagicMock()
        if cmd[0] == "ffprobe":
            res.returncode = 0
            res.stdout = "0.001\n"
            res.stderr = ""
        else:
            res.returncode = 0
            res.stdout = ""
            res.stderr = "size=N/A time=00:01:32.45 bitrate=N/A speed=90x"
        return res

    monkeypatch.setattr("core.pipeline_orchestrator.subprocess.run", fake_run)
    dur = probe_media_duration("fake.webm")
    assert dur == pytest.approx(92.45, abs=0.01)
    assert calls[0][0] == "ffprobe"
    assert calls[1][0] == "ffmpeg"


def test_remux_webm_for_seeking_uses_lossless_copy(tmp_path, monkeypatch):
    src = tmp_path / "in.webm"
    dst = tmp_path / "out.webm"
    src.write_bytes(b"raw-webm-bytes")

    seen_cmd = []

    def fake_run(cmd, **_kwargs):
        seen_cmd.extend(cmd)
        dst.write_bytes(b"remuxed-webm-with-cues")
        res = MagicMock()
        res.returncode = 0
        res.stderr = ""
        return res

    monkeypatch.setattr("core.pipeline_orchestrator.subprocess.run", fake_run)
    ok = remux_webm_for_seeking(str(src), str(dst))
    assert ok is True
    assert "-c" in seen_cmd and "copy" in seen_cmd and "webm" in seen_cmd
