"""Dashboard unit/HTTP contracts. Cursor doubles never connect to any database."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import labeling_store
import master_dashboard_store as dashboard
from schemas.master_dashboard import MasterDashboardResponse


NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
USER_ID = '00000000-0000-0000-0000-000000000001'


class Cursor:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, *params):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return self.row


def empty_payload():
    return dict(
        generatedAt=NOW, activeClients=0, pendingReviewCount=0, publishedVersion=None,
        sessionsWeek=dashboard.week_summary(Cursor((0, 0)), NOW),
        scoreDistribution=dashboard.distribution(Cursor((0, None, None, 0, 0, 0, 0, 0, 0))),
        quality=dict(status='definition_required', agreementPercent=None, kappa=None),
    )


@pytest.mark.parametrize('current,previous,expected,status', [
    (15, 10, 50, 'available'), (0, 10, -100, 'available'),
    (10, 10, 0, 'available'), (3, 0, None, 'no_previous_sessions'),
    (0, 0, None, 'no_previous_sessions'),
])
def test_week_change_and_exact_utc_windows(current, previous, expected, status):
    cursor = Cursor((current, previous))
    result = dashboard.week_summary(cursor, NOW.astimezone(timezone(timedelta(hours=-3))))
    assert result['period'] == {'from': NOW - timedelta(days=7), 'to': NOW}
    assert result['previousPeriod'] == {'from': NOW - timedelta(days=14), 'to': NOW - timedelta(days=7)}
    assert result['changePercent'] == expected
    assert result['changeStatus'] == status
    assert cursor.calls[0][1] == tuple(value.replace(tzinfo=None) for value in (
        NOW - timedelta(days=7), NOW - timedelta(days=7), NOW - timedelta(days=14), NOW))


def test_empty_and_single_score_statistics_and_modal_ties():
    empty = dashboard.distribution(Cursor((0, None, None, 0, 0, 0, 0, 0, 0)))
    assert empty['sampleCount'] == 0
    assert empty['mean'] is None and empty['standardDeviation'] is None
    assert empty['modalRanges'] == []
    single = dashboard.distribution(Cursor((1, 100, 0, 0, 0, 0, 0, 0, 1)))
    assert single['standardDeviation'] == 0 and single['modalRanges'] == ['90–100']
    ties = dashboard.distribution(Cursor((4, 60, 10, 0, 2, 2, 0, 0, 0)))
    assert ties['modalRanges'] == ['50–60', '60–70']
    assert sum(item['count'] for item in ties['bins']) == ties['sampleCount']


def test_invalid_persisted_scores_are_an_error():
    with pytest.raises(HTTPException) as exc:
        dashboard.distribution(Cursor((2, 110, 0, 0, 0, 0, 0, 0, 1)))
    assert exc.value.status_code == 503


def test_distribution_reuses_current_report_selection_and_excludes_deleted_sessions():
    sql = dashboard.DISTRIBUTION_SQL
    assert 'PARTITION BY r.session_id' in sql
    assert 'ORDER BY r.generated_at DESC, r.id DESC' in sql
    assert 'r.is_current = 1' in sql and 'r.report_rank=1' in sql
    assert "s.status='completed' AND s.is_deleted=0" in sql
    assert 'r.overall_score>=90 AND r.overall_score<=100' in sql


def test_queue_count_is_shared_and_independent_of_page_size():
    cursor = Cursor((27,))
    assert labeling_store.count_cases(cursor, status='pending') == 27
    sql, params = cursor.calls[0]
    assert 'TOP' not in sql and 's.is_deleted=0' in sql
    assert params == ('pending',)


@pytest.mark.parametrize('path', ['/api/master/dashboard', '/v1/api/master/dashboard'])
@pytest.mark.parametrize('role', ['spokesperson', 'client_admin', None, 'master_config'])
def test_http_database_role_overrides_claims_and_frontend_input(monkeypatch, path, role):
    cursor = Cursor((USER_ID, None, role) if role else None)

    @contextmanager
    def database(connection):
        assert connection == main.SQL_CONN_STR
        yield cursor

    calls = []
    monkeypatch.setattr(main.master_store, 'database', database)
    monkeypatch.setattr(dashboard, 'dashboard', lambda current: calls.append(current) or empty_payload())
    main.app.dependency_overrides[main.verify_token] = lambda: {
        'oid': USER_ID, 'role': 'master_config', 'clientId': 'untrusted-client',
    }
    try:
        with TestClient(main.app) as client:
            response = client.get(path + '?role=master_config')
        assert response.status_code == (200 if role == 'master_config' else 403)
        assert bool(calls) == (role == 'master_config')
        if role == 'master_config':
            assert response.headers['cache-control'] == 'no-store'
            body = response.json()
            assert body['activeClients'] == 0 and body['pendingReviewCount'] == 0
            assert body['publishedVersion'] is None
            assert body['quality']['kappa'] is None
            assert body['quality']['agreementPercent'] is None
            assert body['sessionsWeek']['period']['to'].endswith('Z')
        else:
            assert isinstance(response.json()['detail'], str)
    finally:
        main.app.dependency_overrides.clear()


def test_missing_and_invalid_auth_are_401(monkeypatch):
    monkeypatch.setattr(main, 'DEV_AUTH', False)
    monkeypatch.setattr(main, '_get_jwks_client', lambda: None)
    with TestClient(main.app) as client:
        for headers in ({}, {'Authorization': 'Bearer invalid'}):
            response = client.get('/api/master/dashboard', headers=headers)
            assert response.status_code == 401
            assert isinstance(response.json()['detail'], str)


def test_database_failure_is_503_never_zero_data(monkeypatch):
    @contextmanager
    def database(_):
        raise HTTPException(503, 'Azure SQL no disponible.')
        yield

    monkeypatch.setattr(main.master_store, 'database', database)
    main.app.dependency_overrides[main.verify_token] = lambda: {'oid': USER_ID}
    try:
        with TestClient(main.app) as client:
            response = client.get('/api/master/dashboard')
        assert response.status_code == 503
        assert 'activeClients' not in response.json()
    finally:
        main.app.dependency_overrides.clear()


def test_contract_forbids_passing_a_target_as_observed_quality():
    from pydantic import ValidationError
    payload = empty_payload()
    payload['quality']['agreementPercent'] = 85
    with pytest.raises(ValidationError):
        MasterDashboardResponse.model_validate(payload)
