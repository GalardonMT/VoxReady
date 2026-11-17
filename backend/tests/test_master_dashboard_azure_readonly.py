"""Opt-in SELECT-only checks against the existing Azure connection. No fixtures are inserted."""
from datetime import datetime, timedelta
import os
from pathlib import Path
from statistics import mean, pstdev
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import master_dashboard_store as dashboard
import labeling_store

pytestmark = pytest.mark.skipif(
    os.getenv('VOXREADY_DASHBOARD_READONLY_AZURE') != '1',
    reason='Explicit opt-in required for Azure SELECT-only checks',
)


def test_real_azure_aggregates_and_queue_consistency():
    with main.master_store.database(main.SQL_CONN_STR) as cursor:
        cursor.execute("SELECT CONVERT(int,SERVERPROPERTY('EngineEdition'))")
        assert cursor.fetchone()[0] in (5, 8), 'Expected the existing Azure SQL connection'
        result = dashboard.dashboard(cursor)
        cursor.execute("SELECT COUNT_BIG(*) FROM dbo.client WHERE status='active' AND is_deleted=0")
        assert result['activeClients'] == cursor.fetchone()[0]
        assert result['pendingReviewCount'] == labeling_store.count_cases(cursor, status='pending')
        cursor.execute("""SELECT COUNT_BIG(*) FROM dbo.[session] s
            WHERE s.status='completed' AND s.is_deleted=0
            AND EXISTS (SELECT 1 FROM dbo.report r
                        WHERE r.session_id=s.id AND r.is_current=1 AND r.overall_score IS NOT NULL)""")
        assert result['scoreDistribution']['sampleCount'] == cursor.fetchone()[0]
        assert sum(item['count'] for item in result['scoreDistribution']['bins']) == result['scoreDistribution']['sampleCount']
        for key, period_key in (('count', 'period'), ('previousCount', 'previousPeriod')):
            period = result['sessionsWeek'][period_key]
            cursor.execute("""SELECT COUNT_BIG(*) FROM dbo.[session]
                WHERE status='completed' AND is_deleted=0 AND finished_at>=? AND finished_at<?""",
                period['from'].replace(tzinfo=None), period['to'].replace(tzinfo=None))
            assert result['sessionsWeek'][key] == cursor.fetchone()[0]


def test_real_database_roles_for_both_http_aliases():
    with main.master_store.database(main.SQL_CONN_STR) as cursor:
        cursor.execute("""SELECT id,role FROM (
            SELECT id,role,ROW_NUMBER() OVER(PARTITION BY role ORDER BY id) AS rank
            FROM dbo.app_user WHERE is_deleted IS NULL OR is_deleted=0
        ) users WHERE rank=1 AND role IN ('master_config','spokesperson','client_admin')""")
        identities = [(str(row[0]), row[1]) for row in cursor.fetchall()]
    assert {role for _, role in identities} == {'master_config', 'spokesperson', 'client_admin'}
    try:
        with TestClient(main.app) as client:
            for identity, role in identities:
                # Only token identity is supplied by the harness. Authorization still
                # resolves the real app_user role and client through the unchanged DB.
                main.app.dependency_overrides[main.verify_token] = lambda identity=identity: {
                    'oid': identity, 'role': 'master_config',
                }
                for path in ('/api/master/dashboard', '/v1/api/master/dashboard'):
                    response = client.get(path)
                    assert response.status_code == (200 if role == 'master_config' else 403)
    finally:
        main.app.dependency_overrides.clear()


def test_tsql_histogram_boundaries_and_historical_report_deduplication():
    # VALUES are query-local input expressions, not tables/databases or persisted
    # test records. Execute the production aggregation on Azure's SQL engine.
    inputs = """WITH ReportInput AS (
        SELECT * FROM (VALUES
            (1,1,999.0,'2026-01-01',0),(2,1,0.0,'2026-01-02',1),
            (3,1,50.0,'2026-01-03',1),(4,2,0.0,'2026-01-01',1),
            (5,3,49.99,'2026-01-01',1),(6,4,60.0,'2026-01-01',1),
            (7,5,70.0,'2026-01-01',1),(8,6,80.0,'2026-01-01',1),
            (9,7,90.0,'2026-01-01',1),(10,8,100.0,'2026-01-01',1),
            (11,9,NULL,'2026-01-01',1),(12,10,33.0,'2026-01-01',1),
            (13,11,33.0,'2026-01-01',1),(14,12,33.0,'2026-01-01',0)
        ) v(id,session_id,overall_score,generated_at,is_current)
    ), SessionInput AS (
        SELECT * FROM (VALUES
            (1,'completed',0),(2,'completed',0),(3,'completed',0),
            (4,'completed',0),(5,'completed',0),(6,'completed',0),
            (7,'completed',0),(8,'completed',0),(9,'completed',0),
            (10,'completed',1),(11,'created',0),(12,'completed',0)
        ) v(id,status,is_deleted)
    ), """
    sql = dashboard.DISTRIBUTION_SQL.lstrip().removeprefix('WITH ')
    sql = inputs + sql.replace('dbo.report', 'ReportInput').replace('dbo.[session]', 'SessionInput')
    with main.master_store.database(main.SQL_CONN_STR) as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()
    scores = [50, 0, 49.99, 60, 70, 80, 90, 100]
    assert row[0] == len(scores)
    assert list(row[3:]) == [2, 1, 1, 1, 1, 2]
    assert row[1] == pytest.approx(mean(scores))
    assert row[2] == pytest.approx(pstdev(scores))


def test_tsql_week_half_open_boundaries():
    inputs = """WITH SessionInput AS (
        SELECT CAST(finished_at AS DATETIME2) AS finished_at,status,is_deleted FROM (VALUES
            ('2026-10-27T12:00:00','completed',0),
            ('2026-11-03T11:59:59','completed',0),
            ('2026-11-03T12:00:00','completed',0),
            ('2026-11-10T11:59:59','completed',0),
            ('2026-11-10T12:00:00','completed',0),
            ('2026-10-27T11:59:59','completed',0),
            ('2026-11-05T12:00:00','completed',1),
            ('2026-11-05T12:00:00','created',0)
        ) v(finished_at,status,is_deleted)
    ) """
    now = datetime(2026, 11, 10, 12)
    start = now - timedelta(days=7)
    with main.master_store.database(main.SQL_CONN_STR) as cursor:
        cursor.execute(inputs + dashboard.WEEK_SQL.replace('dbo.[session]', 'SessionInput'),
                       start, start, start - timedelta(days=7), now)
        assert tuple(cursor.fetchone()) == (2, 2)
