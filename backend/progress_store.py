"""Read model for the authenticated spokesperson's progress screen."""
from datetime import datetime, timezone

from fastapi import HTTPException

import master_topics as store


_CURRENT_REPORTS_CTE = """
WITH CurrentReports AS (
    SELECT r.id, r.session_id, r.overall_score, r.generated_at,
           ROW_NUMBER() OVER (
               PARTITION BY r.session_id
               ORDER BY r.generated_at DESC, r.id DESC
           ) AS report_rank
    FROM dbo.report r
    WHERE r.is_current = 1
)
"""

_COUNT_SQL = _CURRENT_REPORTS_CTE + """
SELECT COUNT_BIG(*)
FROM dbo.session s
JOIN CurrentReports r ON r.session_id = s.id AND r.report_rank = 1
WHERE s.user_id = ? AND s.client_id = ?
  AND s.status = 'completed' AND s.is_deleted = 0
"""

_SESSIONS_SQL = _CURRENT_REPORTS_CTE + """
SELECT TOP (?)
       s.id, s.external_session_id, sc.title AS scenario_title,
       s.started_at, s.finished_at,
       r.id AS report_id, r.overall_score, r.generated_at
FROM dbo.session s
JOIN CurrentReports r ON r.session_id = s.id AND r.report_rank = 1
LEFT JOIN dbo.scenario sc
       ON sc.id = s.scenario_id AND sc.client_id = s.client_id
WHERE s.user_id = ? AND s.client_id = ?
  AND s.status = 'completed' AND s.is_deleted = 0
ORDER BY COALESCE(s.finished_at, r.generated_at, s.updated_at, s.created_at) DESC,
         s.created_at DESC, s.id DESC
"""


def _iso_utc(value):
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("Expected a datetime value from Azure SQL.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _score(value):
    if value is None:
        return None
    return int(round(float(value)))


def _load_area_scores(cursor, report_ids):
    if not report_ids:
        return {}
    placeholders = ",".join("?" for _ in report_ids)
    cursor.execute(
        f"""
        SELECT report_id, area_key, value
        FROM (
            SELECT a.report_id, ra.area_key, a.value,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.report_id, ra.area_key
                       ORDER BY a.id DESC
                   ) AS area_rank
            FROM dbo.area_score a
            JOIN dbo.rubric_area ra ON ra.id = a.rubric_area_id
            WHERE a.report_id IN ({placeholders})
        ) ranked_scores
        WHERE area_rank = 1
        ORDER BY area_key, report_id
        """,
        *report_ids,
    )
    by_report = {report_id: {} for report_id in report_ids}
    for report_id, area_key, value in cursor.fetchall():
        key = str(report_id)
        if key in by_report:
            by_report[key][str(area_key)] = _score(value)
    return by_report


def _session_data(row, scores):
    internal_id, public_id, scenario_title, started_at, finished_at, report_id, overall, generated_at = row
    report_key = str(report_id)
    return {
        "sessionId": str(public_id or internal_id),
        "scenarioTitle": scenario_title or "Escenario no disponible",
        "startedAt": _iso_utc(started_at),
        "completedAt": _iso_utc(finished_at),
        "reportGeneratedAt": _iso_utc(generated_at),
        "overallScore": _score(overall),
        "areas": [
            {"areaKey": area_key, "score": value}
            for area_key, value in sorted(scores.get(report_key, {}).items())
        ],
        "_reportId": report_key,
    }


def get_progress(connection_string, claims, last_n=5):
    """Return progress belonging only to the DB-resolved spokesperson.

    ``last_n`` controls both the trend window and recent-session list. Sessions
    are selected newest-first in SQL, then reversed only for the chart series.
    """
    if isinstance(last_n, bool) or not isinstance(last_n, int) or not 1 <= last_n <= 20:
        raise HTTPException(422, "lastN debe estar entre 1 y 20.")

    with store.database(connection_string) as cursor:
        profile = store.resolve_user(cursor, claims)
        if profile.get("role") != "spokesperson":
            raise HTTPException(403, "Esta vista está disponible solo para el vocero.")
        if not profile.get("id") or not profile.get("client_id"):
            raise HTTPException(403, "El vocero no tiene una empresa asignada.")

        cursor.execute(_COUNT_SQL, profile["id"], profile["client_id"])
        count_row = cursor.fetchone()
        sessions_count = int(count_row[0]) if count_row else 0

        # Aunque el gráfico solicite un solo punto, el delta sigue necesitando
        # la sesión inmediatamente anterior.
        query_limit = max(last_n, 2)
        cursor.execute(_SESSIONS_SQL, query_limit, profile["id"], profile["client_id"])
        rows_desc = list(cursor.fetchall())
        if not rows_desc:
            return {
                "lastN": last_n,
                "sessionsCount": sessions_count,
                "trendSessions": [],
                "areas": [],
                "recentSessions": [],
            }

        report_ids = [str(row[5]) for row in rows_desc]
        scores = _load_area_scores(cursor, report_ids)
        comparison_internal = [_session_data(row, scores) for row in rows_desc]
        recent_internal = comparison_internal[:last_n]
        trend_internal = list(reversed(recent_internal))

        area_keys = sorted(
            {
                area_key
                for session in trend_internal
                for area_key in scores.get(session["_reportId"], {})
            }
        )
        areas = []
        for area_key in area_keys:
            values = [scores.get(session["_reportId"], {}).get(area_key) for session in trend_internal]
            current = scores.get(comparison_internal[0]["_reportId"], {}).get(area_key)
            previous = (
                scores.get(comparison_internal[1]["_reportId"], {}).get(area_key)
                if len(comparison_internal) > 1
                else None
            )
            change = current - previous if current is not None and previous is not None else None
            areas.append(
                {
                    "areaKey": area_key,
                    "current": current,
                    "change": change,
                    "values": values,
                }
            )

        trend_sessions = []
        for index, session in enumerate(trend_internal, start=1):
            trend_sessions.append(
                {
                    "sessionId": session["sessionId"],
                    "label": f"S{index}",
                    "scenarioTitle": session["scenarioTitle"],
                    "completedAt": session["completedAt"],
                    "overallScore": session["overallScore"],
                }
            )

        recent_sessions = []
        for session in recent_internal:
            recent_sessions.append({key: value for key, value in session.items() if key != "_reportId"})

        return {
            "lastN": last_n,
            "sessionsCount": sessions_count,
            "trendSessions": trend_sessions,
            "areas": areas,
            "recentSessions": recent_sessions,
        }
