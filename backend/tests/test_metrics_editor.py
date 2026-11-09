"""Contract and validation checks for the master's metrics editor."""

from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import metrics_store
import metrics_migration
from metrics_catalog import METRICS


def definitions():
    import json
    return [dict(key=item[0], min=item[5], max=item[6], step=item[7],
                 thresholdKeys=json.dumps(list(item[-1]))) for item in METRICS]


def updates():
    return [SimpleNamespace(key=item[0], thresholds=dict(item[-1])) for item in METRICS]


def test_approved_catalog_has_exact_dictionary_and_initial_intervals():
    assert len(METRICS) == len({item[0] for item in METRICS}) == 16
    assert {item[1] for item in METRICS} == {"voice", "vision", "content", "empathy", "governance"}
    assert next(item[-1] for item in METRICS if item[0] == 'voice.hesitation_pause') == {
        'optimalMax': 2, 'warningMax': 5}
    assert next(item[-1] for item in METRICS if item[0] == 'voice.phonation_ratio') == {
        'criticalBelow': 45, 'optimalLow': 60, 'optimalHigh': 85}
    metrics_store._validate(definitions(), updates())


@pytest.mark.parametrize('key,bad', [
    ('voice.wpm', {'warningLow': 100, 'optimalLow': 150, 'optimalHigh': 120, 'warningHigh': 170}),
    ('voice.filler_density', {'optimalMax': 1.55, 'warningMax': 3}),
    ('vision.sway_tolerance', {'optimalMax': 0.015, 'warningMax': 0.081}),
    ('gov.disparity_delta', {'normalBelow': 50, 'auditAt': 35}),
])
def test_invalid_thresholds_rejected(key, bad):
    metrics = updates()
    next(item for item in metrics if item.key == key).thresholds = bad
    with pytest.raises(HTTPException) as exc:
        metrics_store._validate(definitions(), metrics)
    assert exc.value.status_code == 422


def test_missing_duplicate_or_extra_metric_rejected():
    for metrics in (updates()[:-1], updates() + updates()[:1],
                    updates()[:-1] + [SimpleNamespace(key='unknown', thresholds={'x': 2})]):
        with pytest.raises(HTTPException) as exc:
            metrics_store._validate(definitions(), metrics)
        assert exc.value.status_code == 422


def test_master_routes_require_database_role(monkeypatch):
    @contextmanager
    def database(_):
        yield object()

    def reject(_cursor, _claims, master=False):
        assert master is True
        raise HTTPException(403, 'Se requiere el rol master_config.')

    monkeypatch.setattr(main.master_store, 'database', database)
    monkeypatch.setattr(main.master_store, 'resolve_user', reject)
    main.app.dependency_overrides[main.verify_token] = lambda: {'sub': 'speaker'}
    try:
        with TestClient(main.app) as client:
            assert client.get('/v1/api/master/metrics').status_code == 403
            assert client.get('/v1/api/master/metrics/latest').status_code == 403
            assert client.post('/v1/api/master/metrics/draft').status_code == 403
            assert client.put('/v1/api/master/metrics/draft/00000000-0000-0000-0000-000000000001',
                              json={'revision': 1, 'metrics': []}).status_code == 403
            assert client.post('/v1/api/master/metrics/draft/00000000-0000-0000-0000-000000000001/publish',
                               json={'revision': 1}).status_code == 403
            assert client.request('DELETE', '/v1/api/master/metrics/draft/00000000-0000-0000-0000-000000000001',
                                  json={'revision': 1}).status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_clone_published_copies_all_area_columns_and_new_ids():
    class Cursor:
        def __init__(self):
            self.calls = []
        def execute(self, sql, *args):
            self.calls.append((sql, args))
            return self
        def fetchone(self):
            return (4,)

    cursor = Cursor()
    source = '00000000-0000-0000-0000-000000000001'
    version_id = metrics_store.clone_published(cursor, source, notes='test', label='metric-test')
    assert version_id != source
    area_sql, arguments = cursor.calls[1]
    assert 'NEWID(),?,area_key,name,channel,criteria,weight,sort_order' in area_sql
    assert arguments == (version_id, source)
    assert cursor.calls[0][1][1] == 'metric-test'
    assert len(cursor.calls[0][1][1]) <= 20


def test_migration_seeds_new_published_version_once_without_updating_old(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []
            self.catalog = set()
            self.values = 0
            self.source = '00000000-0000-0000-0000-000000000001'
        def execute(self, sql, *args):
            self.calls.append((sql, args))
            self.last_sql = sql
            if 'INSERT INTO dbo.rubric_metric_definition' in sql:
                self.catalog.add(args[0])
            if 'INSERT INTO dbo.rubric_metric_value' in sql:
                self.values += 1
            return self
        def fetchall(self):
            if 'SELECT metric_key FROM dbo.rubric_metric_definition' in self.last_sql:
                return [(key,) for key in self.catalog]
            raise AssertionError(self.last_sql)
        def fetchone(self):
            if 'SELECT COUNT(*) FROM dbo.rubric_metric_value' in self.last_sql:
                return (self.values,)
            if 'SELECT TOP 1 id FROM dbo.rubric_version' in self.last_sql:
                return (self.source,)
            raise AssertionError(self.last_sql)

    clones = []
    def clone(cursor, source_id, *, notes):
        clones.append(source_id)
        return '00000000-0000-0000-0000-000000000002'
    monkeypatch.setattr(metrics_migration, 'clone_published', clone)
    cursor = Cursor()
    metrics_migration.migrate(cursor)
    metrics_migration.migrate(cursor)
    assert clones == [cursor.source]
    assert cursor.values == 16
    assert all(not sql.lstrip().upper().startswith(('UPDATE DBO.RUBRIC_VERSION',
                                                   'DELETE FROM DBO.RUBRIC_VERSION'))
               for sql, _ in cursor.calls)


def test_latest_published_selects_actual_latest_even_if_metrics_missing(monkeypatch):
    class Cursor:
        def execute(self, sql, *args):
            self.sql = sql
            return self
        def fetchone(self):
            return ('00000000-0000-0000-0000-000000000003',)

    cursor = Cursor()
    monkeypatch.setattr(metrics_store, '_version', lambda _cursor, version_id: version_id)
    assert metrics_store.latest_published(cursor) == '00000000-0000-0000-0000-000000000003'
    assert 'JOIN dbo.rubric_metric_value' not in cursor.sql


def test_published_version_number_uses_chronological_order():
    class Cursor:
        def execute(self, sql, *args):
            self.sql = sql
            self.args = args
            return self

        def fetchone(self):
            return (3,)

    cursor = Cursor()
    version_id = '00000000-0000-0000-0000-000000000003'
    assert metrics_store._published_version_number(cursor, version_id) == 3
    assert 'ROW_NUMBER() OVER' in cursor.sql
    assert 'ORDER BY published_at,created_at,id' in cursor.sql
    assert "WHERE status='published'" in cursor.sql
    assert cursor.args == (version_id,)


def test_save_draft_rejects_stale_revision_before_writes():
    class Cursor:
        def execute(self, sql, *args):
            self.sql = sql
            return self
        def fetchone(self):
            return ('00000000-0000-0000-0000-000000000001', 3)
    cursor = Cursor()
    with pytest.raises(HTTPException) as exc:
        metrics_store.save_draft(cursor, '00000000-0000-0000-0000-000000000002', 2, updates())
    assert exc.value.status_code == 409
    assert 'SELECT source_version_id,revision' in cursor.sql


def test_discard_draft_requires_current_revision_and_deletes_only_draft_rows():
    class Cursor:
        def __init__(self):
            self.revision = 4
            self.calls = []
        def execute(self, sql, *args):
            self.calls.append((sql, args))
            return self
        def fetchone(self):
            return ('00000000-0000-0000-0000-000000000001', self.revision)

    cursor = Cursor()
    draft = '00000000-0000-0000-0000-000000000002'
    with pytest.raises(HTTPException) as exc:
        metrics_store.discard_draft(cursor, draft, 3)
    assert exc.value.status_code == 409
    assert len(cursor.calls) == 1

    metrics_store.discard_draft(cursor, draft, 4)
    assert len(cursor.calls) == 4
    assert 'DELETE FROM dbo.rubric_metric_draft_value' in cursor.calls[2][0]
    assert 'DELETE FROM dbo.rubric_metric_draft WHERE' in cursor.calls[3][0]
    assert all('rubric_version' not in sql and 'rubric_metric_value' not in sql
               for sql, _ in cursor.calls[2:])


def test_publish_rejects_stale_source_without_cloning(monkeypatch):
    class Cursor:
        def execute(self, sql, *args):
            self.sql = sql
            return self
        def fetchone(self):
            return ('00000000-0000-0000-0000-000000000003',)
    cursor = Cursor()
    monkeypatch.setattr(metrics_store, '_lock', lambda _cursor: None)
    monkeypatch.setattr(metrics_store, '_require_draft',
                        lambda _cursor, _id, _revision: '00000000-0000-0000-0000-000000000001')
    monkeypatch.setattr(metrics_store, 'clone_published',
                        lambda *_args, **_kwargs: pytest.fail('must not clone stale draft'))
    with pytest.raises(HTTPException) as exc:
        metrics_store.publish_draft(cursor, '00000000-0000-0000-0000-000000000002', 1)
    assert exc.value.status_code == 409


def test_publish_copies_complete_snapshot_then_removes_draft(monkeypatch):
    source = '00000000-0000-0000-0000-000000000001'
    draft = '00000000-0000-0000-0000-000000000002'
    published = '00000000-0000-0000-0000-000000000003'
    import json
    class Cursor:
        def __init__(self):
            self.calls = []
            self.sql = ''
        def execute(self, sql, *args):
            self.sql = sql
            self.calls.append(sql)
            return self
        def fetchone(self):
            if 'SELECT TOP 1 id' in self.sql:
                return (source,)
            if 'SELECT version_label' in self.sql:
                return ('M261021123456-abcde',)
            raise AssertionError(self.sql)
        def fetchall(self):
            if 'rubric_metric_draft_value' in self.sql:
                return [(item[0], json.dumps(item[-1])) for item in METRICS]
            raise AssertionError(self.sql)
    cursor = Cursor()
    monkeypatch.setattr(metrics_store, '_lock', lambda _cursor: None)
    monkeypatch.setattr(metrics_store, '_require_draft', lambda _cursor, _id, _revision: source)
    monkeypatch.setattr(metrics_store, '_catalog', lambda _cursor: definitions())
    monkeypatch.setattr(metrics_store, 'clone_published',
                        lambda _cursor, _source, **_kwargs: published)
    monkeypatch.setattr(metrics_store, '_version', lambda _cursor, version_id: {'id': version_id})
    assert metrics_store.publish_draft(cursor, draft, 2) == {'id': published}
    statements = ' '.join(cursor.calls)
    assert statements.count('INSERT INTO dbo.rubric_metric_value') == 1
    assert cursor.calls.index(next(sql for sql in cursor.calls if 'INSERT INTO dbo.rubric_metric_value' in sql)) < \
        cursor.calls.index(next(sql for sql in cursor.calls if 'DELETE FROM dbo.rubric_metric_draft ' in sql))
    assert any('DELETE FROM dbo.rubric_metric_draft_value' in sql for sql in cursor.calls)


def test_agreement_evaluation_against_dynamic_target(monkeypatch):
    class Cursor:
        def __init__(self, count, avg_ratio):
            self.count = count
            self.avg_ratio = avg_ratio
            self.sql = ''
        def execute(self, sql, *args):
            self.sql = sql
            return self
        def fetchone(self):
            if 'labeling_correction' in self.sql:
                return (self.count, self.avg_ratio)
            return None

    # Caso 1: Insuficiente información (sin muestras)
    c_empty = Cursor(0, None)
    summary_empty = metrics_store.get_ai_human_agreement_summary(c_empty)
    assert summary_empty["status"] == "insufficient_data"
    assert summary_empty["samplesCount"] == 0
    assert summary_empty["aiHumanAgreement"] is None

    # Mock de versión publicada con targets warningLow=0.70, optimalLow=0.85
    fake_published = {
        "metrics": [
            {"key": "gov.agreement_target", "thresholds": {"warningLow": 0.70, "optimalLow": 0.85}}
        ]
    }
    monkeypatch.setattr(metrics_store, "latest_published", lambda _cur: fake_published)

    # Caso 2: Optimal (>= 0.85)
    c_opt = Cursor(10, 0.90)
    summary_opt = metrics_store.get_ai_human_agreement_summary(c_opt)
    assert summary_opt["status"] == "optimal"
    assert summary_opt["aiHumanAgreement"] == 0.90
    assert summary_opt["samplesCount"] == 10

    # Caso 3: Warning (0.70 <= x < 0.85)
    c_warn = Cursor(10, 0.75)
    summary_warn = metrics_store.get_ai_human_agreement_summary(c_warn)
    assert summary_warn["status"] == "warning"
    assert summary_warn["aiHumanAgreement"] == 0.75

    # Caso 4: Critical (< 0.70)
    c_crit = Cursor(10, 0.65)
    summary_crit = metrics_store.get_ai_human_agreement_summary(c_crit)
    assert summary_crit["status"] == "critical"
    assert summary_crit["aiHumanAgreement"] == 0.65


def test_pending_labeling_cases_summary():
    class Cursor:
        def __init__(self):
            pass
        def execute(self, sql, *args):
            return self
        def fetchall(self):
            return [("low_confidence", 3), ("borderline", 5), ("random", 2)]

    c = Cursor()
    res = metrics_store.get_pending_labeling_cases_summary(c)
    assert res["total"] == 10
    assert res["low_confidence"] == 3
    assert res["borderline"] == 5
    assert res["random"] == 2

