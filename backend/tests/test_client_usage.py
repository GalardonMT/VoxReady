"""Usage analytics stay tenant-scoped and expose only aggregate activity."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import client_usage


CLIENT_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"
SCENARIO_ID = "33333333-3333-3333-3333-333333333333"


class UsageCursor:
    def __init__(self):
        self.description = []
        self.marker = ""
        self.calls = []
        self.now = datetime.now(timezone.utc)

    def execute(self, sql, *params):
        self.marker = next(
            marker for marker in (
                "assigned", "summary", "previous", "lessons", "active", "weekly",
                "scenarios", "people", "recent_count", "recent_page",
            ) if f"client_usage_{marker}" in sql
        )
        descriptions = {
            "weekly": ("activityDate", "sessions", "activeSpokespersons"),
            "scenarios": ("scenarioId", "title", "sessions", "activeSpokespersons"),
            "people": ("id", "displayName", "email", "lastActivityAt", "completedSessions", "trainingSeconds"),
            "recent_page": ("id", "type", "displayName", "title", "occurredAt"),
        }
        self.description = [(column,) for column in descriptions.get(self.marker, ())]
        self.calls.append((self.marker, sql, params))
        return self

    def fetchone(self):
        return {
            "assigned": (4,),
            "summary": (5, 3, 1, 1, 3600),
            "previous": (2,),
            "lessons": (2, 600),
            "active": (3,),
            "recent_count": (7,),
        }.get(self.marker)

    def fetchall(self):
        rows = {
            "weekly": [(self.now.date(), 3, 2)],
            "scenarios": [(SCENARIO_ID, "Crisis reputacional", 3, 2)],
            "people": [(USER_ID, "Ana Torres", "ana@example.invalid", self.now - timedelta(days=1), 3, 3600)],
            "recent_page": [
                ("session-1", "session_completed", "Ana Torres", "Crisis reputacional", self.now),
                ("lesson-1", "microlesson_completed", "Ana Torres", "Control del mensaje", self.now - timedelta(hours=1)),
            ],
        }
        return rows.get(self.marker, [])


def test_usage_summary_and_activity_are_aggregated_without_sensitive_content():
    cursor = UsageCursor()
    result = client_usage.get_usage(cursor, CLIENT_ID, days=30)

    assert result["summary"] == {
        "assignedSpokespersons": 4,
        "activeSpokespersons": 3,
        "participationRate": 75,
        "completedSessions": 3,
        "previousCompletedSessions": 2,
        "sessionChangePct": 50,
        "trainingSeconds": 4200,
    }
    assert result["statusBreakdown"] == {"completed": 3, "inProgress": 1, "abandoned": 1}
    assert result["spokespersons"][0]["activityStatus"] == "active"
    assert result["recentActivity"] == []
    assert "recording" not in str(result).lower()
    assert "transcript" not in str(result).lower()
    assert all(CLIENT_ID in call[2] for call in cursor.calls)


def test_usage_filters_are_bound_parameters_in_every_relevant_query():
    cursor = UsageCursor()
    client_usage.get_usage(
        cursor,
        CLIENT_ID,
        days=7,
        user_id=USER_ID,
        scenario_id=SCENARIO_ID,
    )
    calls = {marker: params for marker, _sql, params in cursor.calls}
    for marker in ("summary", "previous", "weekly", "scenarios"):
        assert USER_ID in calls[marker]
        assert SCENARIO_ID in calls[marker]
    for marker in ("lessons", "active"):
        assert USER_ID in calls[marker]
        assert SCENARIO_ID in calls[marker]
    assert calls["people"] == (7, 7, SCENARIO_ID, CLIENT_ID, USER_ID)


def test_recent_activity_is_searchable_and_paginated_inside_the_card():
    cursor = UsageCursor()
    result = client_usage.get_recent_activity(
        cursor,
        CLIENT_ID,
        days=30,
        user_id=USER_ID,
        scenario_id=SCENARIO_ID,
        query="Ana",
        page=2,
        page_size=5,
    )
    assert result["total"] == 7
    assert result["page"] == 2
    assert result["totalPages"] == 2
    assert [item["type"] for item in result["items"]] == [
        "session_completed", "microlesson_completed",
    ]
    calls = {marker: params for marker, _sql, params in cursor.calls}
    for marker in ("recent_count", "recent_page"):
        assert CLIENT_ID in calls[marker]
        assert USER_ID in calls[marker]
        assert SCENARIO_ID in calls[marker]
        assert "Ana" in calls[marker]
    assert calls["recent_page"][-2:] == (5, 5)


class DetailCursor(UsageCursor):
    def execute(self, sql, *params):
        detail_markers = (
            "detail_identity", "detail_activity", "detail_lessons",
            "detail_alerts", "detail_unused_scenarios",
        )
        marker = next((item for item in detail_markers if f"client_spokesperson_{item}" in sql), None)
        if marker:
            self.marker = marker
            self.description = []
            self.calls.append((marker, sql, params))
            return self
        return super().execute(sql, *params)

    def fetchone(self):
        values = {
            "detail_identity": (USER_ID, "Ana Torres", "ana@example.invalid", "es"),
            "detail_activity": (self.now - timedelta(days=2),),
            "detail_lessons": (2, 1),
            "detail_alerts": (2,),
            "detail_unused_scenarios": (1,),
        }
        return values.get(self.marker, super().fetchone())


def test_individual_detail_combines_safe_metrics_and_follow_up_alerts():
    cursor = DetailCursor()
    result = client_usage.get_spokesperson_detail(cursor, CLIENT_ID, USER_ID, days=30)

    assert result["spokesperson"]["id"] == USER_ID
    assert result["spokesperson"]["participationStatus"] == "active"
    assert result["summary"] == {
        "completedSessions": 3,
        "trainingSeconds": 4200,
        "scenariosUsed": 1,
        "completedMicrolessons": 2,
    }
    assert {alert["type"] for alert in result["alerts"]} == {
        "abandoned_sessions", "pending_lessons", "unused_scenarios",
    }
    assert "recording" not in str(result).lower()
    assert "transcript" not in str(result).lower()


class HistoryCursor:
    def __init__(self, *, exists=True):
        self.exists = exists
        self.marker = ""
        self.description = []
        self.now = datetime.now(timezone.utc)
        self.calls = []

    def execute(self, sql, *params):
        if "client_spokesperson_detail_identity" in sql:
            self.marker = "identity"
        elif "client_spokesperson_sessions_count" in sql:
            self.marker = "sessions_count"
        elif "client_spokesperson_sessions_page" in sql:
            self.marker = "sessions_page"
            self.description = [(name,) for name in (
                "id", "scenarioId", "scenarioTitle", "status", "activityAt", "durationSeconds",
            )]
        elif "client_spokesperson_lessons_count" in sql:
            self.marker = "lessons_count"
        elif "client_spokesperson_lessons_page" in sql:
            self.marker = "lessons_page"
            self.description = [(name,) for name in (
                "assignmentId", "id", "title", "scenarioTitle", "status", "durationMinutes",
                "assignedAt", "startedAt", "completedAt",
            )]
        self.calls.append((self.marker, sql, params))
        return self

    def fetchone(self):
        if self.marker == "identity":
            return (USER_ID, "Ana Torres", "ana@example.invalid", "es") if self.exists else None
        if self.marker in ("sessions_count", "lessons_count"):
            return (1,)
        return None

    def fetchall(self):
        if self.marker == "sessions_page":
            return [("session-1", SCENARIO_ID, "Crisis reputacional", "completed", self.now, 420)]
        if self.marker == "lessons_page":
            return [("assignment-1", "lesson-1", "Control del mensaje", "Crisis reputacional", "completed", 5, self.now, self.now, self.now)]
        return []


def test_individual_histories_are_paginated_and_tenant_scoped():
    cursor = HistoryCursor()
    sessions = client_usage.get_spokesperson_sessions(
        cursor, CLIENT_ID, USER_ID, days=30, status="completed", query="Crisis", page=1,
    )
    lessons = client_usage.get_spokesperson_microlessons(
        cursor, CLIENT_ID, USER_ID, days=30, status="completed", query="Control", page=1,
    )

    assert sessions["items"][0]["durationSeconds"] == 420
    assert lessons["items"][0]["status"] == "completed"
    assert all(CLIENT_ID in params for _marker, _sql, params in cursor.calls)
    assert "recording" not in str(sessions).lower()
    session_page_sql = next(sql for marker, sql, _params in cursor.calls if marker == "sessions_page")
    assert "$.metrics.audio.duracionSegundos" in session_page_sql
    assert "media.durationSeconds" in session_page_sql
    assert "DATEDIFF(SECOND,s.started_at" not in session_page_sql


def test_cross_tenant_spokesperson_is_hidden_as_not_found():
    with pytest.raises(HTTPException) as error:
        client_usage.get_spokesperson_sessions(HistoryCursor(exists=False), CLIENT_ID, USER_ID)
    assert error.value.status_code == 404
