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
