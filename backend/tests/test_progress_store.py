"""Unit tests for the spokesperson progress read model."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys

from fastapi import HTTPException
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import progress_store


USER_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"


class ProgressCursor:
    """Small pyodbc-shaped cursor that serves deterministic result sets."""

    def __init__(self, total, sessions, scores=()):
        self.total = total
        self.sessions = sessions
        self.scores = scores
        self.executions = []
        self._rows = []

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        normalized = " ".join(sql.split())
        if "COUNT_BIG(*)" in normalized:
            self._rows = [(self.total,)]
        elif "SELECT TOP (?)" in normalized:
            self._rows = list(self.sessions)
        elif "FROM dbo.area_score" in normalized:
            self._rows = list(self.scores)
        else:
            raise AssertionError(f"Unexpected progress query: {normalized}")
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def dt(day, hour=12):
    return datetime(2026, 10, day, hour, 0, 0)


def session(number, *, score=None, started=None, finished=None):
    """Database row in newest-first query shape."""
    return (
        f"00000000-0000-0000-0000-{number:012d}",
        f"session-public-{number}",
        f"Escenario {number}",
        started or dt(number, 10),
        finished or dt(number, 11),
        f"report-{number}",
        score if score is not None else 60 + number,
        dt(number, 11),
    )


def install_database(monkeypatch, cursor, *, role="spokesperson"):
    @contextmanager
    def database(_connection_string):
        yield cursor

    monkeypatch.setattr(progress_store.store, "database", database)
    monkeypatch.setattr(
        progress_store.store,
        "resolve_user",
        lambda _cursor, _claims: {
            "id": USER_ID,
            "client_id": CLIENT_ID,
            "role": role,
        },
    )


def test_zero_sessions_returns_empty_progress(monkeypatch):
    cursor = ProgressCursor(0, [])
    install_database(monkeypatch, cursor)

    result = progress_store.get_progress("test-db", {"sub": "untrusted"}, 5)

    assert result == {
        "lastN": 5,
        "sessionsCount": 0,
        "trendSessions": [],
        "areas": [],
        "recentSessions": [],
    }
    assert len(cursor.executions) == 2


def test_one_session_has_current_scores_and_null_change(monkeypatch):
    latest = session(1, score=74)
    cursor = ProgressCursor(
        1,
        [latest],
        [
            ("report-1", "expression", 70),
            ("report-1", "voice", 81),
        ],
    )
    install_database(monkeypatch, cursor)

    result = progress_store.get_progress("test-db", {}, 5)

    assert result["trendSessions"][0]["label"] == "S1"
    assert result["trendSessions"][0]["completedAt"] == "2026-10-01T11:00:00Z"
    assert result["areas"] == [
        {"areaKey": "expression", "current": 70, "change": None, "values": [70]},
        {"areaKey": "voice", "current": 81, "change": None, "values": [81]},
    ]
    assert result["recentSessions"][0]["sessionId"] == "session-public-1"
    assert result["recentSessions"][0]["overallScore"] == 74
    assert result["recentSessions"][0]["areas"] == [
        {"areaKey": "expression", "score": 70},
        {"areaKey": "voice", "score": 81},
    ]


def test_one_point_window_still_compares_against_previous_session(monkeypatch):
    cursor = ProgressCursor(
        2,
        [session(2), session(1)],
        [
            ("report-1", "expression", 62),
            ("report-2", "expression", 70),
        ],
    )
    install_database(monkeypatch, cursor)

    result = progress_store.get_progress("test-db", {}, 1)

    assert cursor.executions[1][1][0] == 2
    assert [item["sessionId"] for item in result["trendSessions"]] == ["session-public-2"]
    assert result["areas"] == [
        {"areaKey": "expression", "current": 70, "change": 8, "values": [70]},
    ]
    assert [item["sessionId"] for item in result["recentSessions"]] == ["session-public-2"]


def test_two_sessions_compare_latest_with_immediately_previous(monkeypatch):
    cursor = ProgressCursor(
        2,
        [session(2), session(1)],
        [
            ("report-1", "expression", 62),
            ("report-1", "voice", 88),
            ("report-2", "expression", 70),
            ("report-2", "voice", 81),
        ],
    )
    install_database(monkeypatch, cursor)

    result = progress_store.get_progress("test-db", {}, 5)

    assert [item["sessionId"] for item in result["trendSessions"]] == [
        "session-public-1",
        "session-public-2",
    ]
    assert result["areas"] == [
        {"areaKey": "expression", "current": 70, "change": 8, "values": [62, 70]},
        {"areaKey": "voice", "current": 81, "change": -7, "values": [88, 81]},
    ]
    assert [item["sessionId"] for item in result["recentSessions"]] == [
        "session-public-2",
        "session-public-1",
    ]


def test_more_than_five_uses_selected_window_but_keeps_historical_total(monkeypatch):
    # The SQL query returns the requested latest five, newest first.
    sessions = [session(number) for number in range(8, 3, -1)]
    scores = [(f"report-{number}", "expression", 50 + number) for number in range(4, 9)]
    cursor = ProgressCursor(8, sessions, scores)
    install_database(monkeypatch, cursor)

    result = progress_store.get_progress("test-db", {}, 5)

    assert result["sessionsCount"] == 8
    assert [item["label"] for item in result["trendSessions"]] == ["S1", "S2", "S3", "S4", "S5"]
    assert [item["sessionId"] for item in result["trendSessions"]] == [
        "session-public-4",
        "session-public-5",
        "session-public-6",
        "session-public-7",
        "session-public-8",
    ]
    assert result["areas"][0]["values"] == [54, 55, 56, 57, 58]
    assert result["areas"][0]["change"] == 1
    assert cursor.executions[1][1][0] == 5


def test_missing_area_is_aligned_as_null_and_has_no_delta(monkeypatch):
    cursor = ProgressCursor(
        2,
        [session(2), session(1)],
        [
            ("report-1", "empathy", 55),
            ("report-1", "expression", 60),
            ("report-2", "expression", 64),
            ("report-2", "voice", 72),
        ],
    )
    install_database(monkeypatch, cursor)

    result = progress_store.get_progress("test-db", {}, 5)
    areas = {area["areaKey"]: area for area in result["areas"]}

    assert areas["empathy"] == {
        "areaKey": "empathy", "current": None, "change": None, "values": [55, None]
    }
    assert areas["expression"] == {
        "areaKey": "expression", "current": 64, "change": 4, "values": [60, 64]
    }
    assert areas["voice"] == {
        "areaKey": "voice", "current": 72, "change": None, "values": [None, 72]
    }


@pytest.mark.parametrize("last_n", [0, 21])
def test_last_n_must_be_between_one_and_twenty(last_n):
    with pytest.raises(HTTPException) as error:
        progress_store.get_progress("test-db", {}, last_n)
    assert error.value.status_code == 422


@pytest.mark.parametrize("role", ["client_admin", "master_config"])
def test_only_database_resolved_spokesperson_is_authorized(monkeypatch, role):
    cursor = ProgressCursor(0, [])
    install_database(monkeypatch, cursor, role=role)

    with pytest.raises(HTTPException) as error:
        progress_store.get_progress(
            "test-db",
            {"sub": USER_ID, "role": "spokesperson", "client_id": CLIENT_ID},
            5,
        )

    assert error.value.status_code == 403
    assert cursor.executions == []


def test_queries_are_parameterized_and_scoped_to_resolved_user_and_tenant(monkeypatch):
    cursor = ProgressCursor(1, [session(1)], [("report-1", "expression", 70)])
    install_database(monkeypatch, cursor)

    progress_store.get_progress(
        "test-db",
        {"sub": "attacker", "client_id": "other-client", "user_id": "other-user"},
        5,
    )

    count_sql, count_params = cursor.executions[0]
    sessions_sql, sessions_params = cursor.executions[1]
    scores_sql, scores_params = cursor.executions[2]
    for sql in (count_sql, sessions_sql):
        compact = " ".join(sql.split())
        assert "s.user_id = ?" in compact
        assert "s.client_id = ?" in compact
        assert "s.status = 'completed'" in compact
        assert "s.is_deleted = 0" in compact
        assert "r.is_current = 1" in compact
        assert "ROW_NUMBER() OVER" in compact
        assert "r.generated_at DESC, r.id DESC" in compact
        assert "attacker" not in sql and "other-client" not in sql
    assert count_params == (USER_ID, CLIENT_ID)
    assert sessions_params == (5, USER_ID, CLIENT_ID)
    assert "FROM dbo.area_score" in scores_sql
    assert "a.report_id IN (?)" in scores_sql
    assert scores_params == ("report-1",)


def test_naive_and_aware_datetimes_are_serialized_as_utc(monkeypatch):
    row = session(
        1,
        started=datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
        finished=datetime(2026, 10, 1, 10),
    )
    cursor = ProgressCursor(1, [row], [("report-1", "expression", 70)])
    install_database(monkeypatch, cursor)

    recent = progress_store.get_progress("test-db", {}, 5)["recentSessions"][0]

    assert recent["startedAt"] == "2026-10-01T09:00:00Z"
    assert recent["completedAt"] == "2026-10-01T10:00:00Z"
    assert recent["reportGeneratedAt"] == "2026-10-01T11:00:00Z"
