"""Parameterized Azure SQL store for dbo.session_turn."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import pyodbc

from .migration import normalize_sql_conn_str

logger = logging.getLogger("interview_live.store")


def _safe_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _connect(conn_str: str):
    return pyodbc.connect(normalize_sql_conn_str(conn_str), timeout=12)


def get_turn_by_index(conn_str: str, session_id: str, turn_index: int) -> dict[str, Any] | None:
    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, session_id, session_question_id, parent_turn_id,
                   base_sequence_no, turn_index, followup_depth, turn_kind,
                   question_text, followup_generated, followup_question_text,
                   followup_trigger_reason, start_offset_ms, end_offset_ms,
                   audio_duration_sec, speech_time_sec, phonation_ratio,
                   transcript, asr_status, gemini_latency_ms,
                   ffmpeg_latency_ms, parakeet_latency_ms
            FROM dbo.session_turn
            WHERE session_id = ? AND turn_index = ?
            """,
            session_id,
            turn_index,
        )
        row = cur.fetchone()
        return _row_to_turn_dict(row) if row else None


def list_session_turns(conn_str: str, session_id: str) -> list[dict[str, Any]]:
    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, session_id, session_question_id, parent_turn_id,
                   base_sequence_no, turn_index, followup_depth, turn_kind,
                   question_text, followup_generated, followup_question_text,
                   followup_trigger_reason, start_offset_ms, end_offset_ms,
                   audio_duration_sec, speech_time_sec, phonation_ratio,
                   transcript, asr_status, gemini_latency_ms,
                   ffmpeg_latency_ms, parakeet_latency_ms
            FROM dbo.session_turn
            WHERE session_id = ?
            ORDER BY turn_index ASC
            """,
            session_id,
        )
        return [_row_to_turn_dict(row) for row in cur.fetchall()]


def count_followups_generated_for_base(
    conn_str: str, session_id: str, base_sequence_no: int
) -> int:
    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM dbo.session_turn
            WHERE session_id = ?
              AND base_sequence_no = ?
              AND (turn_kind = 'follow_up' OR followup_generated = 1)
            """,
            session_id,
            base_sequence_no,
        )
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0


def create_turn(
    conn_str: str,
    *,
    session_id: str,
    session_question_id: str | None,
    parent_turn_id: str | None,
    base_sequence_no: int,
    turn_index: int,
    followup_depth: int,
    turn_kind: str,
    question_text: str,
    start_offset_ms: int | None,
    end_offset_ms: int | None,
    audio_mime_type: str | None,
    audio_bytes: int,
) -> tuple[str, bool]:
    """Insert a new turn row idempotently. Returns (turn_id, already_existed)."""
    turn_id = str(uuid.uuid4())
    safe_sq_id = _safe_uuid(session_question_id)
    safe_parent_id = _safe_uuid(parent_turn_id)

    try:
        with _connect(conn_str) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.session_turn (
                    id, session_id, session_question_id, parent_turn_id,
                    base_sequence_no, turn_index, followup_depth, turn_kind,
                    question_text, start_offset_ms, end_offset_ms,
                    audio_mime_type, audio_bytes, asr_status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending',
                        SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                (
                    turn_id,
                    session_id,
                    safe_sq_id,
                    safe_parent_id,
                    base_sequence_no,
                    turn_index,
                    followup_depth,
                    turn_kind,
                    question_text,
                    start_offset_ms,
                    end_offset_ms,
                    audio_mime_type,
                    audio_bytes,
                ),
            )
            conn.commit()
            return turn_id, False
    except pyodbc.IntegrityError:
        existing = get_turn_by_index(conn_str, session_id, turn_index)
        if existing:
            return existing["turnId"], True
        raise


def update_turn_followup(
    conn_str: str,
    *,
    turn_id: str,
    has_followup: bool,
    followup_question: str | None,
    trigger_reason: str | None,
    gemini_latency_ms: int | None,
) -> None:
    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.session_turn
            SET followup_generated = ?,
                followup_question_text = ?,
                followup_trigger_reason = ?,
                gemini_latency_ms = ?,
                updated_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (
                1 if has_followup else 0,
                followup_question,
                trigger_reason,
                gemini_latency_ms,
                turn_id,
            ),
        )
        conn.commit()


def mark_turn_asr_processing(conn_str: str, turn_id: str) -> None:
    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.session_turn
            SET asr_status = 'processing', updated_at = SYSUTCDATETIME()
            WHERE id = ? AND asr_status = 'pending'
            """,
            turn_id,
        )
        conn.commit()


def update_turn_asr_completed(
    conn_str: str,
    *,
    turn_id: str,
    session_id: str,
    session_question_id: str | None,
    base_sequence_no: int,
    turn_kind: str,
    transcript: str,
    words: list[dict[str, Any]],
    acoustic_metrics: dict[str, Any],
    ffmpeg_latency_ms: int | None,
    parakeet_latency_ms: int | None,
) -> None:
    words_json = json.dumps(words, ensure_ascii=False)
    pauses_json = json.dumps(
        acoustic_metrics.get("pausas_prolongadas_acusticas", []), ensure_ascii=False
    )

    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.session_turn
            SET transcript = ?,
                words_json = ?,
                audio_duration_sec = ?,
                speech_time_sec = ?,
                silence_time_sec = ?,
                phonation_ratio = ?,
                acoustic_pauses_json = ?,
                ffmpeg_latency_ms = ?,
                parakeet_latency_ms = ?,
                asr_status = 'completed',
                asr_error = NULL,
                updated_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (
                transcript,
                words_json,
                acoustic_metrics.get("total_duration_sec"),
                acoustic_metrics.get("speech_time_sec"),
                acoustic_metrics.get("silence_time_sec"),
                acoustic_metrics.get("phonation_ratio"),
                pauses_json,
                ffmpeg_latency_ms,
                parakeet_latency_ms,
                turn_id,
            ),
        )

        # Espejar respuesta del turno base en dbo.session_question por retrocompatibilidad
        if turn_kind == "base" and transcript:
            safe_sq_id = _safe_uuid(session_question_id)
            if safe_sq_id:
                cur.execute(
                    """
                    UPDATE dbo.session_question
                    SET response_text = ?, updated_at = SYSUTCDATETIME()
                    WHERE id = ? AND session_id = ?
                    """,
                    (transcript, safe_sq_id, session_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE dbo.session_question
                    SET response_text = ?, updated_at = SYSUTCDATETIME()
                    WHERE session_id = ? AND sequence_no = ?
                    """,
                    (transcript, session_id, base_sequence_no),
                )

        conn.commit()


def update_turn_asr_failed(
    conn_str: str,
    *,
    turn_id: str,
    error_message: str,
    ffmpeg_latency_ms: int | None = None,
    parakeet_latency_ms: int | None = None,
) -> None:
    with _connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.session_turn
            SET asr_status = 'failed',
                asr_error = ?,
                ffmpeg_latency_ms = COALESCE(?, ffmpeg_latency_ms),
                parakeet_latency_ms = COALESCE(?, parakeet_latency_ms),
                updated_at = SYSUTCDATETIME()
            WHERE id = ?
            """,
            (error_message[:490], ffmpeg_latency_ms, parakeet_latency_ms, turn_id),
        )
        conn.commit()


def _row_to_turn_dict(row) -> dict[str, Any]:
    return {
        "turnId": str(row[0]),
        "sessionId": str(row[1]),
        "sessionQuestionId": str(row[2]) if row[2] else None,
        "parentTurnId": str(row[3]) if row[3] else None,
        "baseSequenceNo": int(row[4]),
        "turnIndex": int(row[5]),
        "followupDepth": int(row[6]),
        "turnKind": str(row[7]),
        "questionText": str(row[8]),
        "followupGenerated": bool(row[9]),
        "followupQuestionText": row[10],
        "followupTriggerReason": row[11],
        "startOffsetMs": row[12],
        "endOffsetMs": row[13],
        "audioDurationSec": row[14],
        "speechTimeSec": row[15],
        "phonationRatio": row[16],
        "transcript": row[17],
        "asrStatus": str(row[18]),
        "geminiLatencyMs": row[19],
        "ffmpegLatencyMs": row[20],
        "parakeetLatencyMs": row[21],
    }
