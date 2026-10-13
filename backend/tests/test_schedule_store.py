"""Agenda del vocero: reglas de dominio y aislamiento antes del cableado HTTP."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schedule_store
from schemas.schedule import ScheduleCreateRequest, ScheduleUpdateRequest


USER_ID = "00112233-4455-6677-8899-aabbccddeeff"
CLIENT_ID = "11112233-4455-6677-8899-aabbccddeeff"
SCENARIO_ID = "22112233-4455-6677-8899-aabbccddeeff"
SCHEDULE_ID = "33112233-4455-6677-8899-aabbccddeeff"
SESSION_ID = "44112233-4455-6677-8899-aabbccddeeff"
REPORT_ID = "55112233-4455-6677-8899-aabbccddeeff"


@pytest.fixture
def cursor(monkeypatch):
    current = MagicMock()

    @contextmanager
    def database(_connection_string):
        yield current

    monkeypatch.setattr(schedule_store.store, "database", database)
    monkeypatch.setattr(
        schedule_store.store,
        "resolve_user",
        lambda *_args, **_kwargs: {
            "id": USER_ID,
            "client_id": CLIENT_ID,
            "role": "spokesperson",
        },
    )
    return current


def test_request_models_require_date_and_scenario_and_forbid_extra_fields():
    payload = ScheduleCreateRequest(date="2026-10-12", scenarioId=SCENARIO_ID)
    assert payload.date == date(2026, 10, 12)
    assert str(payload.scenario_id) == SCENARIO_ID

    with pytest.raises(ValidationError):
        ScheduleCreateRequest(date="2026-10-12")
    with pytest.raises(ValidationError):
        ScheduleCreateRequest(date="2026-10-12", scenarioId=SCENARIO_ID, status="completed")
    with pytest.raises(ValidationError):
        ScheduleUpdateRequest()
    with pytest.raises(ValidationError):
        ScheduleUpdateRequest(status="cancelled")


def test_only_database_resolved_spokesperson_can_use_schedule(monkeypatch, cursor):
    monkeypatch.setattr(
        schedule_store.store,
        "resolve_user",
        lambda *_args, **_kwargs: {
            "id": USER_ID,
            "client_id": CLIENT_ID,
            "role": "client_admin",
        },
    )

    with pytest.raises(HTTPException) as error:
        schedule_store.list_calendar(
            "test-db", {"sub": "forged-user", "role": "spokesperson"},
            date(2026, 10, 1), date(2026, 10, 31),
        )

    assert error.value.status_code == 403
    cursor.execute.assert_not_called()


@pytest.mark.parametrize(
    "scheduled_date",
    [date(2026, 10, 11), date(2027, 10, 13)],
    ids=["past", "beyond-twelve-months"],
)
def test_create_rejects_dates_outside_today_through_twelve_months(cursor, scheduled_date):
    with pytest.raises(HTTPException) as error:
        schedule_store.create_schedule(
            "test-db", {"sub": "untrusted"}, scheduled_date, SCENARIO_ID,
            today=date(2026, 10, 12),
        )

    assert error.value.status_code == 422
    cursor.execute.assert_not_called()


def test_create_accepts_today_and_requires_active_scenario_from_same_client(cursor):
    cursor.fetchone.side_effect = [
        ("topic-id",),
        ("topic-id",),
        (SCENARIO_ID, "Declaración de crisis"),
    ]

    result = schedule_store.create_schedule(
        "test-db", {"sub": "external-identity"}, date(2026, 10, 12), SCENARIO_ID,
        today=date(2026, 10, 12),
    )

    assert result == {
        "id": result["id"],
        "date": "2026-10-12",
        "status": "scheduled",
        "scenario": {"id": SCENARIO_ID, "title": "Declaración de crisis", "status": "active", "available": True},
        "sessionId": None,
    }
    topic_lookup, topic_lock, scenario_call, insert_call = cursor.execute.call_args_list
    assert topic_lookup.args[1:] == (SCENARIO_ID, CLIENT_ID)
    assert "WITH (UPDLOCK,HOLDLOCK)" in topic_lock.args[0]
    assert "s.client_id=?" in scenario_call.args[0]
    assert "s.status='active'" in scenario_call.args[0]
    assert "WITH (UPDLOCK,HOLDLOCK)" in scenario_call.args[0]
    assert scenario_call.args[1:] == (SCENARIO_ID, CLIENT_ID)
    assert "INSERT INTO dbo.schedule" in insert_call.args[0]
    assert insert_call.args[2:] == (CLIENT_ID, USER_ID, date(2026, 10, 12), SCENARIO_ID)


def test_create_hides_missing_archived_or_cross_tenant_scenario(cursor):
    cursor.fetchone.return_value = None

    with pytest.raises(HTTPException) as error:
        schedule_store.create_schedule(
            "test-db", {}, date(2026, 11, 1), SCENARIO_ID,
            today=date(2026, 10, 12),
        )

    assert error.value.status_code == 404
    assert cursor.execute.call_count == 1


def test_list_returns_visible_schedules_and_completed_sessions_with_current_report(cursor):
    completed_at = datetime(2026, 10, 1, 15, 30, tzinfo=timezone.utc)
    generated_at = datetime(2026, 10, 1, 15, 31, tzinfo=timezone.utc)
    created_at = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    cursor.fetchall.side_effect = [
        [
            (
                SCHEDULE_ID, date(2026, 10, 15), "scheduled", SCENARIO_ID, None,
                None, created_at, updated_at, "Escenario archivado", "archived", 0,
                "active", 0,
            )
        ],
        [
            (
                SESSION_ID, "session-public-1", completed_at, SCENARIO_ID,
                "Escenario histórico", REPORT_ID, 81, generated_at,
                "expression", 70,
            ),
            (
                SESSION_ID, "session-public-1", completed_at, SCENARIO_ID,
                "Escenario histórico", REPORT_ID, 81, generated_at,
                "voice", 81,
            ),
        ],
    ]

    result = schedule_store.list_calendar(
        "test-db", {"sub": "external-identity"},
        date(2026, 10, 1), date(2026, 10, 31),
    )

    assert result["dateFrom"] == "2026-10-01"
    assert result["dateTo"] == "2026-10-31"
    assert result["schedules"][0]["scenario"] == {
        "id": SCENARIO_ID,
        "title": "Escenario archivado",
        "status": "archived",
        "available": False,
    }
    assert result["sessions"] == [
        {
            "sessionId": "session-public-1",
            "date": "2026-10-01",
            "completedAt": "2026-10-01T15:30:00+00:00",
            "scenario": {"id": SCENARIO_ID, "title": "Escenario histórico"},
            "report": {
                "id": REPORT_ID,
                "overallScore": 81,
                "generatedAt": "2026-10-01T15:31:00+00:00",
                "areas": [
                    {"key": "expression", "value": 70},
                    {"key": "voice", "value": 81},
                ],
            },
        }
    ]
    schedule_call, session_call = cursor.execute.call_args_list
    assert "sch.user_id=? AND sch.client_id=?" in schedule_call.args[0]
    assert "sch.status IN ('scheduled','completed')" in schedule_call.args[0]
    assert "sc.status='active'" not in schedule_call.args[0]
    assert schedule_call.args[1:] == (USER_ID, CLIENT_ID, date(2026, 10, 1), date(2026, 10, 31))
    assert "s.user_id=? AND s.client_id=?" in session_call.args[0]
    assert "r.is_current=1" in session_call.args[0]
    assert session_call.args[1:] == (USER_ID, CLIENT_ID, date(2026, 10, 1), date(2026, 10, 31))


def test_list_rejects_inverted_range_before_query(cursor):
    with pytest.raises(HTTPException) as error:
        schedule_store.list_calendar("test-db", {}, date(2026, 11, 1), date(2026, 10, 1))

    assert error.value.status_code == 422
    cursor.execute.assert_not_called()


def test_list_rejects_ranges_longer_than_366_inclusive_days(cursor):
    with pytest.raises(HTTPException) as error:
        schedule_store.list_calendar("test-db", {}, date(2026, 1, 1), date(2027, 1, 2))

    assert error.value.status_code == 422
    cursor.execute.assert_not_called()


def test_patch_changes_date_and_scenario_only_for_scheduled_unlinked_item(cursor):
    cursor.fetchone.side_effect = [
        ("topic-id",),
        ("topic-id",),
        (SCENARIO_ID, "Escenario nuevo"),
        (
            SCHEDULE_ID, date(2026, 10, 15), "scheduled", SCENARIO_ID, None,
            "Escenario anterior", "active", 0, "active", 0,
        ),
    ]

    result = schedule_store.update_schedule(
        "test-db", {}, SCHEDULE_ID,
        scheduled_date=date(2026, 10, 20), scenario_id=SCENARIO_ID,
        today=date(2026, 10, 12),
    )

    assert result["date"] == "2026-10-20"
    assert result["scenario"]["title"] == "Escenario nuevo"
    topic_lookup, topic_lock, scenario_call, owned_call, update_call = cursor.execute.call_args_list
    assert topic_lookup.args[1:] == (SCENARIO_ID, CLIENT_ID)
    assert "WITH (UPDLOCK,HOLDLOCK)" in topic_lock.args[0]
    assert scenario_call.args[1:] == (SCENARIO_ID, CLIENT_ID)
    assert "WITH (UPDLOCK,HOLDLOCK)" in owned_call.args[0]
    assert owned_call.args[1:] == (SCHEDULE_ID, USER_ID, CLIENT_ID)
    assert "SET scheduled_date=?,scenario_id=?,updated_at=SYSUTCDATETIME()" in update_call.args[0]
    assert update_call.args[1:] == (date(2026, 10, 20), SCENARIO_ID, SCHEDULE_ID, USER_ID, CLIENT_ID)


@pytest.mark.parametrize(
    "status,session_id",
    [("cancelled", None), ("completed", SESSION_ID), ("scheduled", SESSION_ID)],
)
def test_patch_rejects_non_scheduled_or_linked_item(cursor, status, session_id):
    cursor.fetchone.return_value = (
        SCHEDULE_ID, date(2026, 10, 15), status, SCENARIO_ID, session_id,
        "Escenario", "active", 0, "active", 0,
    )

    with pytest.raises(HTTPException) as error:
        schedule_store.update_schedule(
            "test-db", {}, SCHEDULE_ID, scheduled_date=date(2026, 10, 20),
            today=date(2026, 10, 12),
        )

    assert error.value.status_code == 409
    assert cursor.execute.call_count == 1


def test_patch_other_user_or_client_is_opaque_not_found(cursor):
    cursor.fetchone.return_value = None

    with pytest.raises(HTTPException) as error:
        schedule_store.update_schedule(
            "test-db", {}, SCHEDULE_ID, scheduled_date=date(2026, 10, 20),
            today=date(2026, 10, 12),
        )

    assert error.value.status_code == 404
    assert "user_id=? AND sch.client_id=?" in cursor.execute.call_args.args[0]


def test_cancel_is_status_update_not_delete(cursor):
    cursor.fetchone.return_value = (
        SCHEDULE_ID, date(2026, 10, 15), "scheduled", SCENARIO_ID, None,
        "Escenario", "active", 0, "active", 0,
    )

    result = schedule_store.cancel_schedule("test-db", {}, SCHEDULE_ID)

    assert result["status"] == "cancelled"
    sql = cursor.execute.call_args_list[-1].args[0]
    assert "UPDATE dbo.schedule SET status='cancelled'" in sql
    assert "DELETE" not in sql.upper()
    assert cursor.execute.call_args_list[-1].args[1:] == (SCHEDULE_ID, USER_ID, CLIENT_ID)


def test_start_creates_and_links_one_spanish_session_atomically(monkeypatch, cursor):
    cursor.fetchone.return_value = (
        SCHEDULE_ID, "scheduled", SCENARIO_ID, None,
        None, None, None, None,
    )
    cursor.rowcount = 1
    created = {
        "sessionId": "session-public-1",
        "session_id": "session-public-1",
        "scenarioId": SCENARIO_ID,
        "scenario_id": SCENARIO_ID,
        "status": "created",
        "questionCount": 4,
    }
    create = MagicMock(return_value=(created, SESSION_ID))
    monkeypatch.setattr(schedule_store.spokesperson_store, "create_session_in_transaction", create)

    result = schedule_store.start_schedule("test-db", {}, SCHEDULE_ID)

    assert result["sessionId"] == "session-public-1"
    assert result["scheduleId"] == SCHEDULE_ID
    create.assert_called_once_with(
        cursor,
        {"id": USER_ID, "client_id": CLIENT_ID, "role": "spokesperson"},
        SCENARIO_ID,
        "es",
        "schedule:" + SCHEDULE_ID,
    )
    applock_sql = cursor.execute.call_args_list[1].args[0]
    assert "sp_getapplock" in applock_sql
    select_sql = cursor.execute.call_args_list[2].args[0]
    assert "sch.user_id=? AND sch.client_id=?" in select_sql
    update = cursor.execute.call_args_list[-1]
    assert "status='scheduled' AND session_id IS NULL AND scenario_id=?" in update.args[0]
    assert update.args[1:] == (SESSION_ID, SCHEDULE_ID, USER_ID, CLIENT_ID, SCENARIO_ID)


def test_start_double_click_returns_already_linked_session(monkeypatch, cursor):
    cursor.fetchone.side_effect = [
        (
            SCHEDULE_ID, "scheduled", SCENARIO_ID, SESSION_ID,
            SESSION_ID, SCENARIO_ID, "created", "session-public-1",
        ),
        (4,),
    ]
    create = MagicMock()
    monkeypatch.setattr(schedule_store.spokesperson_store, "create_session_in_transaction", create)

    result = schedule_store.start_schedule("test-db", {}, SCHEDULE_ID)

    assert result["sessionId"] == "session-public-1"
    assert result["scheduleId"] == SCHEDULE_ID
    assert result["questionCount"] == 4
    create.assert_not_called()
    assert not any("INSERT INTO dbo.session" in call.args[0] for call in cursor.execute.call_args_list)


def test_start_rejects_foreign_cancelled_or_changed_schedule(monkeypatch, cursor):
    create = MagicMock()
    monkeypatch.setattr(schedule_store.spokesperson_store, "create_session_in_transaction", create)

    cursor.fetchone.return_value = None
    with pytest.raises(HTTPException) as missing:
        schedule_store.start_schedule("test-db", {}, SCHEDULE_ID)
    assert missing.value.status_code == 404

    cursor.reset_mock()
    cursor.fetchone.return_value = (
        SCHEDULE_ID, "cancelled", SCENARIO_ID, None,
        None, None, None, None,
    )
    with pytest.raises(HTTPException) as cancelled:
        schedule_store.start_schedule("test-db", {}, SCHEDULE_ID)
    assert cancelled.value.status_code == 409
    create.assert_not_called()


def test_start_rolls_back_when_schedule_changes_before_link(monkeypatch, cursor):
    cursor.fetchone.return_value = (
        SCHEDULE_ID, "scheduled", SCENARIO_ID, None,
        None, None, None, None,
    )
    cursor.rowcount = 0
    monkeypatch.setattr(
        schedule_store.spokesperson_store,
        "create_session_in_transaction",
        lambda *_args, **_kwargs: ({"sessionId": "session-public-1"}, SESSION_ID),
    )

    with pytest.raises(HTTPException) as changed:
        schedule_store.start_schedule("test-db", {}, SCHEDULE_ID)

    assert changed.value.status_code == 409
