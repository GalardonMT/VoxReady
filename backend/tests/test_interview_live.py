"""Unit tests for backend/interview_live (policy, Gemini audio, router, cache, background ASR)."""

from __future__ import annotations

import asyncio
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from interview_live import store
from interview_live.audio_background import compute_turn_rms_acoustics, process_turn_audio_background
from interview_live.config import InterviewLiveSettings, get_follow_up_policy, get_settings
from interview_live.context_cache import SessionContextCache, SessionInterviewContext
from interview_live.gemini_followup import (
    SYSTEM_INSTRUCTION,
    FollowUpEvaluationResult,
    GeminiFollowUpService,
    build_followup_prompt,
)
from interview_live.router import create_interview_live_router
from interview_live.schemas import GeminiFollowUpDecision


def _make_context(difficulty: str = "intermediate") -> SessionInterviewContext:
    policy = get_follow_up_policy(difficulty)
    return SessionInterviewContext(
        session_id="00112233-4455-6677-8899-aabbccddeeff",
        scenario_id="11111111-2222-3333-4444-555555555555",
        scenario_title="Fuga en planta industrial",
        difficulty=policy.difficulty,
        policy=policy,
        topic_id="22222222-3333-4444-5555-666666666666",
        topic_context="Incidente operativo con vecinos cercanos preocupados.",
        topic_optics="empathetic",
        topic_audience="leadership",
        key_messages=("La seguridad de la comunidad es nuestra máxima prioridad.",),
        red_lines=("No confirmar negligencia sin peritaje oficial.",),
        base_questions=(
            {
                "sessionQuestionId": "33333333-4444-5555-6666-777777777777",
                "questionId": "44444444-5555-6666-7777-888888888888",
                "sequenceNo": 1,
                "text": "¿Por qué no evacuaron antes a los vecinos?",
            },
            {
                "sessionQuestionId": "55555555-6666-7777-8888-999999999999",
                "questionId": "66666666-7777-8888-9999-000000000000",
                "sequenceNo": 2,
                "text": "¿Qué compensación ofrecerán a las familias afectadas?",
            },
        ),
    )


def _make_settings(tmp_path: Path, **overrides) -> InterviewLiveSettings:
    defaults = dict(
        gemini_api_key="fake-gemini-key",
        gemini_followup_model="gemini-3.5-flash-lite",
        gemini_timeout_sec=12.0,
        nvidia_api_key="fake-nvidia-key",
        nvidia_riva_server="grpc.nvcf.nvidia.com:443",
        nvidia_function_id="fn-test",
        nvidia_language_code="es-US",
        max_audio_bytes=1024 * 1024,
        bg_concurrency=2,
        context_cache_ttl_sec=1800,
        context_cache_max_entries=128,
        tmp_dir=tmp_path,
    )
    defaults.update(overrides)
    return InterviewLiveSettings(**defaults)


def test_difficulty_policy_matches_approved_rules():
    basic = get_follow_up_policy("basic")
    assert basic.enabled is False
    assert basic.max_per_base_question == 0

    inter = get_follow_up_policy("intermediate")
    assert inter.enabled is True
    assert inter.max_per_base_question == 1
    assert inter.pressure_level == "moderate"

    hard = get_follow_up_policy("hard")
    assert hard.enabled is True
    assert hard.max_per_base_question == 1
    assert hard.pressure_level == "high_red_line_focus"

    # Spanish aliases map safely
    assert get_follow_up_policy("Fácil").difficulty == "basic"
    assert get_follow_up_policy("Difícil").difficulty == "hard"
    assert get_settings().gemini_timeout_sec == 12.0


def test_gemini_decision_schema_sanitizes_and_hard_prompt_focuses_red_lines():
    d_empty = GeminiFollowUpDecision.model_validate({"hasFollowUp": True, "followUpQuestion": "   "})
    assert d_empty.hasFollowUp is False
    assert d_empty.followUpQuestion is None

    d_valid = GeminiFollowUpDecision.model_validate(
        {
            "hasFollowUp": True,
            "followUpQuestion": "¿Admite entonces que falló el protocolo de alerta temprana?",
            "triggerReason": "presion_linea_roja",
        }
    )
    assert d_valid.hasFollowUp is True
    assert d_valid.triggerReason == "flanco_linea_roja"
    assert "protocolo" in d_valid.followUpQuestion

    # Short/invalid question clears triggerReason to keep hasFollowUp=False invariant
    d_short = GeminiFollowUpDecision.model_validate(
        {"hasFollowUp": True, "followUpQuestion": "ok", "triggerReason": "evasion"}
    )
    assert d_short.hasFollowUp is False
    assert d_short.triggerReason is None

    # Long multi-sentence output trims cleanly at sentence boundary without mid-sentence "..."
    long_q = (
        "¿Por qué no activaron la sirena comunitaria apenas detectaron la fuga en el reactor principal? "
        + ("Además quisiéramos conocer cada detalle administrativo del turno nocturno y los correos internos " * 3)
    )
    d_trimmed = GeminiFollowUpDecision.model_validate(
        {"hasFollowUp": True, "followUpQuestion": long_q, "triggerReason": "evasion"}
    )
    assert d_trimmed.hasFollowUp is True
    assert d_trimmed.triggerReason == "evasion_nucleo"
    assert len(d_trimmed.followUpQuestion) <= 240
    assert d_trimmed.followUpQuestion.endswith("?")
    assert not d_trimmed.followUpQuestion.endswith("...")

    prompt_hard = build_followup_prompt(
        ctx=_make_context("hard"),
        current_question="¿Por qué no evacuaron antes a los vecinos?",
        previous_turns=[],
        current_base_sequence_no=1,
    )
    assert "ALTA PRESIÓN SOBRE LÍNEAS ROJAS" in prompt_hard
    assert "No confirmar negligencia" in prompt_hard
    assert "[Pregunta base #2] ¿Qué compensación ofrecerán a las familias afectadas?" in prompt_hard
    assert "DATO NO CONFIABLE" in SYSTEM_INSTRUCTION

    prompt_last = build_followup_prompt(
        ctx=_make_context("intermediate"),
        current_question="¿Qué compensación ofrecerán a las familias afectadas?",
        previous_turns=[],
        current_base_sequence_no=2,
    )
    assert "(No quedan preguntas base posteriores en la pauta)" in prompt_last


def test_gemini_degrades_safely_on_timeout_or_error(tmp_path):
    settings = _make_settings(tmp_path, gemini_timeout_sec=0.05)
    ctx = _make_context("hard")

    # API exception -> degraded=True, has_follow_up=False
    svc_err = GeminiFollowUpService(settings=settings)
    with patch.object(svc_err, "_call_gemini_sync", side_effect=RuntimeError("503 high demand")):
        res = asyncio.run(
            svc_err.evaluate_turn_audio(
                ctx=ctx,
                current_question="¿Qué falló?",
                audio_bytes=b"0" * 1024,
                mime_type="audio/webm;codecs=opus",
                previous_turns=[],
            )
        )
    assert res.has_follow_up is False
    assert res.follow_up_question is None
    assert res.degraded is True

    # Timeout -> degraded=True, has_follow_up=False
    import time as _time

    def slow_call(**_kwargs):
        _time.sleep(0.25)
        return GeminiFollowUpDecision(hasFollowUp=True, followUpQuestion="¿Pregunta tardía?")

    svc_slow = GeminiFollowUpService(settings=settings)
    with patch.object(svc_slow, "_call_gemini_sync", side_effect=slow_call):
        res_to = asyncio.run(
            svc_slow.evaluate_turn_audio(
                ctx=ctx,
                current_question="¿Qué falló?",
                audio_bytes=b"0" * 1024,
                mime_type="audio/webm",
                previous_turns=[],
            )
        )
    assert res_to.has_follow_up is False
    assert res_to.degraded is True


def test_context_cache_lru_and_ttl():
    cache = SessionContextCache(ttl_seconds=60, max_entries=2)
    c1, c2, c3 = _make_context("basic"), _make_context("intermediate"), _make_context("hard")
    cache.put("s1", c1)
    cache.put("s2", c2)
    assert cache.get("s1") is c1
    cache.put("s3", c3)
    assert cache.get("s2") is None  # evicted LRU
    assert cache.get("s1") is c1
    assert cache.get("s3") is c3


def _build_test_client(tmp_path, *, difficulty: str, followup_result: FollowUpEvaluationResult | None = None, session_status: str = "created"):
    ctx = _make_context(difficulty)
    cache = SessionContextCache()
    cache.put(ctx.session_id, ctx)

    fake_followup_svc = MagicMock(spec=GeminiFollowUpService)
    eval_res = followup_result or FollowUpEvaluationResult(
        has_follow_up=True,
        follow_up_question="¿Por qué no alertaron a la comunidad en los primeros diez minutos?",
        trigger_reason="evasion",
        degraded=False,
        latency_ms=420,
    )

    async def _eval(**_kwargs):
        return eval_res

    fake_followup_svc.evaluate_turn_audio.side_effect = _eval

    app = FastAPI()
    router = create_interview_live_router(
        sql_conn_str_getter=lambda: "Driver={SQL Server};Server=fake;",
        verify_token_dep=lambda: {"sub": "user-1"},
        require_session_access_fn=lambda _cs, _u, sid, read_only=False: {
            "id": ctx.session_id,
            "status": session_status,
            "external_session_id": sid,
        },
        settings_getter=lambda: _make_settings(tmp_path),
        context_cache=cache,
        followup_service_factory=lambda _s: fake_followup_svc,
    )
    app.include_router(router)
    return TestClient(app), fake_followup_svc, ctx


def test_router_basic_skips_gemini_and_schedules_bg(tmp_path, monkeypatch):
    client, fake_svc, _ctx = _build_test_client(tmp_path, difficulty="basic")
    bg_calls = []
    monkeypatch.setattr(store, "get_turn_by_index", lambda *_a, **_k: None)
    monkeypatch.setattr(store, "list_session_turns", lambda *_a, **_k: [])
    monkeypatch.setattr(store, "create_turn", lambda *_a, **_k: ("turn-1", False))
    monkeypatch.setattr(
        "interview_live.router.schedule_turn_audio_background",
        lambda **kw: bg_calls.append(kw),
    )

    resp = client.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("turn_1.webm", b"x" * 2048, "audio/webm")},
        data={
            "baseSequenceNo": "1",
            "turnIndex": "1",
            "turnKind": "base",
            "questionText": "¿Por qué no evacuaron antes?",
            "startOffsetMs": "1000",
            "endOffsetMs": "9000",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hasFollowUp"] is False
    assert body["remainingFollowUpsForBase"] == 0
    assert fake_svc.evaluate_turn_audio.call_count == 0
    assert len(bg_calls) == 1


def test_router_hard_triggers_single_followup_and_blocks_chaining(tmp_path, monkeypatch):
    client, fake_svc, _ctx = _build_test_client(tmp_path, difficulty="hard")
    updates = []
    monkeypatch.setattr(store, "get_turn_by_index", lambda *_a, **_k: None)
    monkeypatch.setattr(store, "list_session_turns", lambda *_a, **_k: [])
    monkeypatch.setattr(store, "create_turn", lambda *_a, **_k: ("turn-1", False))
    monkeypatch.setattr(store, "update_turn_followup", lambda *_a, **kw: updates.append(kw))
    monkeypatch.setattr("interview_live.router.schedule_turn_audio_background", lambda **_kw: None)

    resp1 = client.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("turn_1.webm", b"x" * 2048, "audio/webm")},
        data={
            "baseSequenceNo": "1",
            "turnIndex": "1",
            "turnKind": "base",
            "questionText": "¿Por qué no evacuaron antes?",
        },
    )
    assert resp1.status_code == 200
    b1 = resp1.json()
    assert b1["hasFollowUp"] is True
    assert b1["remainingFollowUpsForBase"] == 0
    assert fake_svc.evaluate_turn_audio.call_count == 1
    assert len(updates) == 1 and updates[0]["has_followup"] is True

    # Follow-up turn (turnKind='follow_up') must NOT trigger a 2nd chained follow-up
    monkeypatch.setattr(
        store,
        "list_session_turns",
        lambda *_a, **_k: [
            {
                "turnId": "turn-1",
                "baseSequenceNo": 1,
                "turnIndex": 1,
                "turnKind": "base",
                "followupGenerated": True,
                "questionText": "¿Por qué no evacuaron antes?",
                "transcript": "Activamos el protocolo.",
            }
        ],
    )
    monkeypatch.setattr(store, "create_turn", lambda *_a, **_k: ("turn-2", False))
    resp2 = client.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("turn_2.webm", b"y" * 2048, "audio/webm")},
        data={
            "baseSequenceNo": "1",
            "turnIndex": "2",
            "turnKind": "follow_up",
            "parentTurnId": "turn-1",
            "questionText": b1["followUpQuestion"],
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["hasFollowUp"] is False
    assert fake_svc.evaluate_turn_audio.call_count == 1  # still 1, not called again


def test_router_guards_status_mime_size_and_idempotency(tmp_path, monkeypatch):
    # 409 on finished session
    client_done, _, _ = _build_test_client(tmp_path, difficulty="intermediate", session_status="analyzing")
    r_409 = client_done.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("t.webm", b"x" * 1024, "audio/webm")},
        data={"baseSequenceNo": "1", "turnIndex": "1", "turnKind": "base", "questionText": "Pregunta"},
    )
    assert r_409.status_code == 409

    # 415 on invalid MIME & 413 on oversized upload
    client, _, _ = _build_test_client(tmp_path, difficulty="intermediate")
    r_415 = client.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("t.txt", b"hello", "text/plain")},
        data={"baseSequenceNo": "1", "turnIndex": "1", "turnKind": "base", "questionText": "Pregunta"},
    )
    assert r_415.status_code == 415

    r_413 = client.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("big.webm", b"x" * (1024 * 1024 + 10), "audio/webm")},
        data={"baseSequenceNo": "1", "turnIndex": "1", "turnKind": "base", "questionText": "Pregunta"},
    )
    assert r_413.status_code == 413

    # Idempotent replay
    monkeypatch.setattr(
        store,
        "get_turn_by_index",
        lambda *_a, **_k: {
            "turnId": "existing-turn",
            "turnIndex": 1,
            "baseSequenceNo": 1,
            "turnKind": "base",
            "followupGenerated": True,
            "followupQuestionText": "¿Puede precisar el horario?",
            "followupTriggerReason": "evasion",
            "asrStatus": "completed",
            "geminiLatencyMs": 310,
        },
    )
    monkeypatch.setattr(store, "count_followups_generated_for_base", lambda *_a, **_k: 1)
    r_idem = client.post(
        "/v1/interview-live/sessions/sess-1/turns",
        files={"audio": ("t.webm", b"x" * 1024, "audio/webm")},
        data={"baseSequenceNo": "1", "turnIndex": "1", "turnKind": "base", "questionText": "Pregunta"},
    )
    assert r_idem.status_code == 200
    assert r_idem.json()["idempotentReplay"] is True
    assert r_idem.json()["turnId"] == "existing-turn"


def test_background_audio_processing_and_cleanup(tmp_path, monkeypatch):
    # Generate a tiny real 16kHz PCM WAV with speech + silence to test RMS acoustics directly
    wav_file = tmp_path / "sample.wav"
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16)
    silence = np.zeros(sr * 2, dtype=np.int16)
    samples = np.concatenate([tone, silence, tone])
    with wave.open(str(wav_file), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())

    ac = compute_turn_rms_acoustics(wav_file)
    assert ac["total_duration_sec"] == pytest.approx(4.0, abs=0.05)
    assert ac["speech_time_sec"] == pytest.approx(2.0, abs=0.15)
    assert len(ac["pausas_prolongadas_acusticas"]) == 1

    # Verify process_turn_audio_background cleans temp files and persists completion
    completed_calls = []
    monkeypatch.setattr(store, "mark_turn_asr_processing", lambda *_a, **_k: None)
    monkeypatch.setattr(store, "update_turn_asr_completed", lambda *_a, **kw: completed_calls.append(kw))
    monkeypatch.setattr(
        "interview_live.audio_background.convert_to_pcm16_wav",
        lambda _in, out_wav: (out_wav.write_bytes(wav_file.read_bytes()), 45)[1],
    )
    monkeypatch.setattr(
        "interview_live.audio_background.transcribe_wav_with_parakeet",
        lambda _w, _s: ("hola mundo", [{"word": "hola", "start": 0.1, "end": 0.5, "confidence": 0.94}], 120),
    )

    settings = _make_settings(tmp_path / "run_tmp")
    asyncio.run(
        process_turn_audio_background(
            conn_str="fake",
            settings=settings,
            turn_id="t-1",
            session_id="s-1",
            session_question_id="sq-1",
            base_sequence_no=1,
            turn_kind="base",
            audio_bytes=b"webm-bytes",
            audio_mime_type="audio/webm",
        )
    )
    assert len(completed_calls) == 1
    assert completed_calls[0]["transcript"] == "hola mundo"
    assert not list((tmp_path / "run_tmp").glob("*"))  # temp files cleaned up
