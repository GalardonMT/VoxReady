"""Read-through TTL/LRU cache for immutable session context metadata."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import pyodbc

from .config import FollowUpPolicy, get_follow_up_policy, normalize_difficulty
from .migration import normalize_sql_conn_str

logger = logging.getLogger("interview_live.context_cache")


@dataclass(frozen=True)
class SessionInterviewContext:
    session_id: str
    scenario_id: str
    scenario_title: str
    difficulty: str
    policy: FollowUpPolicy
    topic_id: str
    topic_context: str
    topic_optics: str
    topic_audience: str
    key_messages: tuple[str, ...]
    red_lines: tuple[str, ...]
    base_questions: tuple[dict, ...]


class SessionContextCache:
    """In-memory TTL + LRU cache for immutable scenario/topic context per session.

    Mutable turn state (follow-up counts, turn history, ASR status) is ALWAYS
    stored and read from Azure SQL (dbo.session_turn) so multi-replica ACA
    deployments remain strictly consistent.
    """

    def __init__(self, ttl_seconds: int = 1800, max_entries: int = 512):
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, SessionInterviewContext]] = OrderedDict()

    def get(self, session_id: str) -> SessionInterviewContext | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(session_id)
            if entry is None:
                return None
            expires_at, ctx = entry
            if now >= expires_at:
                self._items.pop(session_id, None)
                return None
            self._items.move_to_end(session_id)
            return ctx

    def put(self, session_id: str, ctx: SessionInterviewContext) -> None:
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            self._items[session_id] = (expires_at, ctx)
            self._items.move_to_end(session_id)
            while len(self._items) > self._max_entries:
                self._items.popitem(last=False)

    def invalidate(self, session_id: str) -> None:
        with self._lock:
            self._items.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def get_or_load(self, conn_str: str, session_id: str) -> SessionInterviewContext:
        cached = self.get(session_id)
        if cached is not None:
            return cached
        ctx = load_session_context_from_sql(conn_str, session_id)
        self.put(session_id, ctx)
        return ctx


def load_session_context_from_sql(conn_str: str, session_id: str) -> SessionInterviewContext:
    """Load immutable scenario, topic, key messages, red lines, and base questions."""
    normalized = normalize_sql_conn_str(conn_str)
    with pyodbc.connect(normalized, timeout=10) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.id, sc.id, sc.title, sc.difficulty,
                   t.id, t.context, t.optics, t.audience
            FROM dbo.session s
            JOIN dbo.scenario sc ON sc.id = s.scenario_id AND sc.is_deleted = 0
            JOIN dbo.topic t ON t.id = sc.topic_id AND t.is_deleted = 0
            WHERE s.id = ? AND s.is_deleted = 0
            """,
            session_id,
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"No se encontró contexto de escenario para la sesión {session_id}.")

        resolved_session_id = str(row[0])
        scenario_id = str(row[1])
        scenario_title = str(row[2] or "Simulación de Vocería en Crisis")
        difficulty = normalize_difficulty(row[3])
        policy = get_follow_up_policy(difficulty)
        topic_id = str(row[4])
        topic_context = str(row[5] or "")
        topic_optics = str(row[6] or "formal")
        topic_audience = str(row[7] or "leadership")

        cur.execute(
            """
            SELECT text
            FROM dbo.topic_key_message
            WHERE topic_id = ? AND (status IS NULL OR status = 'active')
            ORDER BY sort_order ASC
            """,
            topic_id,
        )
        key_messages = tuple(str(r[0]).strip() for r in cur.fetchall() if r[0])

        cur.execute(
            """
            SELECT text
            FROM dbo.topic_red_line
            WHERE topic_id = ? AND (status IS NULL OR status = 'active')
            ORDER BY sort_order ASC
            """,
            topic_id,
        )
        red_lines = tuple(str(r[0]).strip() for r in cur.fetchall() if r[0])

        cur.execute(
            """
            SELECT sq.id, sq.question_id, sq.sequence_no, q.text
            FROM dbo.session_question sq
            JOIN dbo.question q ON q.id = sq.question_id
            WHERE sq.session_id = ?
            ORDER BY sq.sequence_no ASC
            """,
            resolved_session_id,
        )
        base_questions = tuple(
            {
                "sessionQuestionId": str(r[0]),
                "questionId": str(r[1]),
                "sequenceNo": int(r[2]),
                "text": str(r[3]),
            }
            for r in cur.fetchall()
        )

    return SessionInterviewContext(
        session_id=resolved_session_id,
        scenario_id=scenario_id,
        scenario_title=scenario_title,
        difficulty=difficulty,
        policy=policy,
        topic_id=topic_id,
        topic_context=topic_context,
        topic_optics=topic_optics,
        topic_audience=topic_audience,
        key_messages=key_messages,
        red_lines=red_lines,
        base_questions=base_questions,
    )
