"""SQL aggregates for the master dashboard; never writes or returns histories.

Approved ticket rules: completed sessions by finished_at, rolling seven-day UTC
windows, and all-time completed/non-deleted sessions with one current report.
Client status affects the active-client counter only, preserving historical data
and the existing progress/labeling populations. Quality has no approved formula.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

import labeling_store
import metrics_store
from progress_store import _CURRENT_REPORTS_CTE


WEEK_SQL = """
SELECT COUNT_BIG(CASE WHEN finished_at>=? THEN 1 END),
       COUNT_BIG(CASE WHEN finished_at<? THEN 1 END)
FROM dbo.[session]
WHERE status='completed' AND is_deleted=0
  AND finished_at>=? AND finished_at<?
"""

# Reuse the progress screen's deterministic selection of one current report.
DISTRIBUTION_SQL = _CURRENT_REPORTS_CTE + """
SELECT COUNT_BIG(r.overall_score),
       AVG(CAST(r.overall_score AS FLOAT)),
       STDEVP(CAST(r.overall_score AS FLOAT)),
       COUNT_BIG(CASE WHEN r.overall_score>=0 AND r.overall_score<50 THEN 1 END),
       COUNT_BIG(CASE WHEN r.overall_score>=50 AND r.overall_score<60 THEN 1 END),
       COUNT_BIG(CASE WHEN r.overall_score>=60 AND r.overall_score<70 THEN 1 END),
       COUNT_BIG(CASE WHEN r.overall_score>=70 AND r.overall_score<80 THEN 1 END),
       COUNT_BIG(CASE WHEN r.overall_score>=80 AND r.overall_score<90 THEN 1 END),
       COUNT_BIG(CASE WHEN r.overall_score>=90 AND r.overall_score<=100 THEN 1 END)
FROM dbo.[session] s
JOIN CurrentReports r ON r.session_id=s.id AND r.report_rank=1
WHERE s.status='completed' AND s.is_deleted=0
"""

BIN_BOUNDS = ((0, 50, '<50'), (50, 60, '50–60'), (60, 70, '60–70'),
              (70, 80, '70–80'), (80, 90, '80–90'), (90, 100, '90–100'))


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def week_summary(cursor, now):
    now = utc(now)
    start = now - timedelta(days=7)
    previous_start = start - timedelta(days=7)
    # Azure DATETIME2 stores naive UTC, as in the existing labeling store.
    start_sql, previous_sql, end_sql = (value.replace(tzinfo=None) for value in (start, previous_start, now))
    cursor.execute(WEEK_SQL, start_sql, start_sql, previous_sql, end_sql)
    current, previous = map(int, cursor.fetchone())
    return {
        'timezone': 'UTC',
        'period': {'from': start, 'to': now},
        'previousPeriod': {'from': previous_start, 'to': start},
        'count': current,
        'previousCount': previous,
        'changePercent': round(100 * (current - previous) / previous, 2) if previous else None,
        'changeStatus': 'available' if previous else 'no_previous_sessions',
    }


def distribution(cursor):
    cursor.execute(DISTRIBUTION_SQL)
    row = cursor.fetchone()
    sample_count = int(row[0])
    bins = [dict(label=label, lowerBound=lower, upperBound=upper,
                 upperInclusive=upper == 100, count=int(count))
            for (lower, upper, label), count in zip(BIN_BOUNDS, row[3:])]
    if sum(item['count'] for item in bins) != sample_count:
        # Invalid persisted scores are a data error, never an invented zero.
        raise HTTPException(503, 'Hay puntajes fuera del rango permitido para el panel.')
    maximum = max(item['count'] for item in bins)
    return {
        'population': 'all_completed_current_reports',
        'sampleCount': sample_count,
        'bins': bins,
        'mean': float(row[1]) if row[1] is not None else None,
        'standardDeviation': float(row[2]) if row[2] is not None else None,
        'standardDeviationKind': 'population',
        'modalRanges': [item['label'] for item in bins if maximum and item['count'] == maximum],
    }


def dashboard(cursor):
    cursor.execute('SELECT SYSUTCDATETIME()')
    now = utc(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT_BIG(*) FROM dbo.client WHERE status='active' AND is_deleted=0")
    active_clients = int(cursor.fetchone()[0])
    weekly = week_summary(cursor, now)
    pending = labeling_store.count_cases(cursor, status='pending')
    published = metrics_store.latest_published(cursor)
    version = None if published is None else {
        key: published[key] for key in ('id', 'versionLabel', 'versionNumber', 'publishedAt')
    }
    if version and version['publishedAt']:
        version['publishedAt'] = utc(datetime.fromisoformat(version['publishedAt']))
    return {
        'generatedAt': now,
        'activeClients': active_clients,
        'sessionsWeek': weekly,
        'pendingReviewCount': pending,
        'publishedVersion': version,
        'scoreDistribution': distribution(cursor),
        'quality': {'status': 'definition_required', 'agreementPercent': None, 'kappa': None},
    }
