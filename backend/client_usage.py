"""Read-only usage analytics for an authenticated client administrator."""
from datetime import datetime, timezone

from fastapi import HTTPException


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(value)


def _rows(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _filters(user_id=None, scenario_id=None, alias="s"):
    sql = ""
    params = []
    if user_id:
        sql += f" AND {alias}.user_id=?"
        params.append(str(user_id))
    if scenario_id:
        sql += f" AND {alias}.scenario_id=?"
        params.append(str(scenario_id))
    return sql, params


def _spokesperson(cursor, client_id, spokesperson_id):
    """Resolve a spokesperson inside the authenticated tenant without leaking existence."""
    cursor.execute(
        """/* client_spokesperson_detail_identity */
        SELECT id,display_name AS displayName,email,preferred_language AS preferredLanguage
        FROM dbo.app_user
        WHERE id=? AND client_id=? AND role='spokesperson' AND ISNULL(is_deleted,0)=0""",
        str(spokesperson_id),
        str(client_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Vocero no encontrado.")
    return {
        "id": str(row[0]),
        "displayName": row[1],
        "email": row[2],
        "preferredLanguage": row[3] or "es",
    }


def _page(total, page, page_size):
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(page, total_pages)
    return safe_page, total_pages, (safe_page - 1) * page_size


def get_usage(cursor, client_id, *, days=30, user_id=None, scenario_id=None):
    """Aggregate usage without exposing recordings, transcripts, or answers."""
    client_id = str(client_id)
    session_filter, session_params = _filters(user_id, scenario_id)

    cursor.execute(
        """/* client_usage_assigned */
        SELECT COUNT_BIG(*)
        FROM dbo.app_user
        WHERE client_id=? AND role='spokesperson'
          AND (is_deleted IS NULL OR is_deleted=0)""",
        client_id,
    )
    assigned_row = cursor.fetchone()
    assigned = int(assigned_row[0]) if assigned_row else 0

    cursor.execute(
        f"""/* client_usage_summary */
        SELECT
          COUNT_BIG(*) AS totalSessions,
          SUM(CASE WHEN s.status='completed' THEN 1 ELSE 0 END) AS completedSessions,
          SUM(CASE WHEN s.status IN ('failed','cancelled') THEN 1 ELSE 0 END) AS abandonedSessions,
          SUM(CASE WHEN s.status NOT IN ('completed','failed','cancelled') THEN 1 ELSE 0 END) AS inProgressSessions,
          COALESCE(SUM(CASE WHEN s.status='completed'
            THEN COALESCE(media.durationSeconds,0) ELSE 0 END),0) AS sessionSeconds
        FROM dbo.session s
        OUTER APPLY (
          SELECT TOP 1 TRY_CONVERT(DECIMAL(12,3),COALESCE(
            JSON_VALUE(apr.summary_json,'$.metrics.audio.duracionSegundos'),
            JSON_VALUE(apr.summary_json,'$.metrics.audio.duracion_segundos')
          )) AS durationSeconds
          FROM dbo.analysis_job aj
          JOIN dbo.analysis_pipeline_result apr ON apr.analysis_job_id=aj.id
          WHERE aj.session_id=s.id AND apr.pipeline='fusion' AND ISJSON(apr.summary_json)=1
          ORDER BY apr.created_at DESC,apr.id DESC
        ) media
        WHERE s.client_id=? AND ISNULL(s.is_deleted,0)=0
          AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
          {session_filter}""",
        client_id,
        days,
        *session_params,
    )
    summary_row = cursor.fetchone() or (0, 0, 0, 0, 0)

    cursor.execute(
        f"""/* client_usage_previous */
        SELECT COUNT_BIG(*)
        FROM dbo.session s
        WHERE s.client_id=? AND ISNULL(s.is_deleted,0)=0 AND s.status='completed'
          AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
          AND COALESCE(s.finished_at,s.updated_at,s.created_at)<DATEADD(DAY,-?,SYSUTCDATETIME())
          {session_filter}""",
        client_id,
        days * 2,
        days,
        *session_params,
    )
    previous_row = cursor.fetchone()
    previous_completed = int(previous_row[0]) if previous_row else 0

    lesson_filter = ""
    lesson_params = []
    if user_id:
        lesson_filter += " AND ma.user_id=?"
        lesson_params.append(str(user_id))
    if scenario_id:
        lesson_filter += " AND ml.scenario_id=?"
        lesson_params.append(str(scenario_id))
    cursor.execute(
        f"""/* client_usage_lessons */
        SELECT COUNT_BIG(DISTINCT ma.user_id),
               COALESCE(SUM(CASE WHEN ma.status='completed' THEN COALESCE(ml.duration_minutes,0)*60 ELSE 0 END),0)
        FROM dbo.microlesson_assignment ma
        JOIN dbo.microlesson ml ON ml.id=ma.microlesson_id AND ml.client_id=ma.client_id
        WHERE ma.client_id=? AND ma.status IN ('in_progress','completed')
          AND COALESCE(ma.completed_at,ma.started_at,ma.updated_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
          {lesson_filter}""",
        client_id,
        days,
        *lesson_params,
    )
    lesson_row = cursor.fetchone() or (0, 0)

    cursor.execute(
        f"""/* client_usage_active */
        SELECT COUNT_BIG(DISTINCT activity.userId)
        FROM (
          SELECT s.user_id AS userId
          FROM dbo.session s
          WHERE s.client_id=? AND ISNULL(s.is_deleted,0)=0
            AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
            {session_filter}
          UNION ALL
          SELECT ma.user_id
          FROM dbo.microlesson_assignment ma
          JOIN dbo.microlesson ml ON ml.id=ma.microlesson_id AND ml.client_id=ma.client_id
          WHERE ma.client_id=? AND ma.status IN ('in_progress','completed')
            AND COALESCE(ma.completed_at,ma.started_at,ma.updated_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
            {lesson_filter}
        ) activity""",
        client_id,
        days,
        *session_params,
        client_id,
        days,
        *lesson_params,
    )
    active_row = cursor.fetchone()
    active = int(active_row[0]) if active_row else 0

    cursor.execute(
        f"""/* client_usage_weekly */
        SELECT CAST(COALESCE(s.finished_at,s.updated_at,s.created_at) AS date) AS activityDate,
               COUNT_BIG(*) AS sessions,
               COUNT_BIG(DISTINCT s.user_id) AS activeSpokespersons
        FROM dbo.session s
        WHERE s.client_id=? AND ISNULL(s.is_deleted,0)=0
          AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
          {session_filter}
        GROUP BY CAST(COALESCE(s.finished_at,s.updated_at,s.created_at) AS date)
        ORDER BY activityDate""",
        client_id,
        days,
        *session_params,
    )
    trend = _rows(cursor)
    for item in trend:
        item["activityDate"] = _iso(item["activityDate"])
        item["sessions"] = int(item["sessions"])
        item["activeSpokespersons"] = int(item["activeSpokespersons"])

    cursor.execute(
        f"""/* client_usage_scenarios */
        SELECT sc.id AS scenarioId,sc.title,
               COUNT_BIG(*) AS sessions,
               COUNT_BIG(DISTINCT s.user_id) AS activeSpokespersons
        FROM dbo.session s
        JOIN dbo.scenario sc ON sc.id=s.scenario_id AND sc.client_id=s.client_id
        WHERE s.client_id=? AND ISNULL(s.is_deleted,0)=0
          AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
          {session_filter}
        GROUP BY sc.id,sc.title
        ORDER BY sessions DESC,sc.title""",
        client_id,
        days,
        *session_params,
    )
    scenarios = _rows(cursor)
    for item in scenarios:
        item["scenarioId"] = str(item["scenarioId"])
        item["sessions"] = int(item["sessions"])
        item["activeSpokespersons"] = int(item["activeSpokespersons"])

    person_filter = " AND u.id=?" if user_id else ""
    person_params = [str(user_id)] if user_id else []
    scenario_join_filter = " AND s.scenario_id=?" if scenario_id else ""
    scenario_join_params = [str(scenario_id)] if scenario_id else []
    cursor.execute(
        f"""/* client_usage_people */
        SELECT u.id,u.display_name AS displayName,u.email,
               MAX(COALESCE(s.finished_at,s.updated_at,s.created_at)) AS lastActivityAt,
               SUM(CASE WHEN s.status='completed' AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME()) THEN 1 ELSE 0 END) AS completedSessions,
               COALESCE(SUM(CASE WHEN s.status='completed' AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
                 THEN COALESCE(media.durationSeconds,0) ELSE 0 END),0) AS trainingSeconds
        FROM dbo.app_user u
        LEFT JOIN dbo.session s ON s.user_id=u.id AND s.client_id=u.client_id
          AND ISNULL(s.is_deleted,0)=0 {scenario_join_filter}
        OUTER APPLY (
          SELECT TOP 1 TRY_CONVERT(DECIMAL(12,3),COALESCE(
            JSON_VALUE(apr.summary_json,'$.metrics.audio.duracionSegundos'),
            JSON_VALUE(apr.summary_json,'$.metrics.audio.duracion_segundos')
          )) AS durationSeconds
          FROM dbo.analysis_job aj
          JOIN dbo.analysis_pipeline_result apr ON apr.analysis_job_id=aj.id
          WHERE aj.session_id=s.id AND apr.pipeline='fusion' AND ISJSON(apr.summary_json)=1
          ORDER BY apr.created_at DESC,apr.id DESC
        ) media
        WHERE u.client_id=? AND u.role='spokesperson' AND ISNULL(u.is_deleted,0)=0 {person_filter}
        GROUP BY u.id,u.display_name,u.email
        ORDER BY u.display_name,u.email,u.id""",
        days,
        days,
        *scenario_join_params,
        client_id,
        *person_params,
    )
    people = _rows(cursor)
    now = datetime.now(timezone.utc)
    for item in people:
        item["id"] = str(item["id"])
        last = item["lastActivityAt"]
        if last is None:
            item["activityStatus"] = "not_started"
        else:
            aware = last.replace(tzinfo=timezone.utc) if isinstance(last, datetime) and last.tzinfo is None else last
            inactive_days = (now - aware.astimezone(timezone.utc)).days if isinstance(aware, datetime) else 999
            item["activityStatus"] = "active" if inactive_days <= 14 else "low_activity"
        item["lastActivityAt"] = _iso(last)
        item["completedSessions"] = int(item["completedSessions"] or 0)
        item["trainingSeconds"] = int(item["trainingSeconds"] or 0)

    completed = int(summary_row[1] or 0)
    change = None if previous_completed == 0 else round((completed - previous_completed) * 100 / previous_completed)
    total_seconds = int(summary_row[4] or 0) + int(lesson_row[1] or 0)
    return {
        "periodDays": days,
        "summary": {
            "assignedSpokespersons": assigned,
            "activeSpokespersons": active,
            "participationRate": round(active * 100 / assigned) if assigned else 0,
            "completedSessions": completed,
            "previousCompletedSessions": previous_completed,
            "sessionChangePct": change,
            "trainingSeconds": total_seconds,
        },
        "statusBreakdown": {
            "completed": completed,
            "inProgress": int(summary_row[3] or 0),
            "abandoned": int(summary_row[2] or 0),
        },
        "trend": trend,
        "scenarios": scenarios,
        "spokespersons": people,
        "recentActivity": [],
    }


def get_recent_activity(
    cursor,
    client_id,
    *,
    days=30,
    user_id=None,
    scenario_id=None,
    query="",
    page=1,
    page_size=5,
):
    """Return a tenant-scoped, searchable page of recent activity."""
    client_id = str(client_id)
    session_filter, session_params = _filters(user_id, scenario_id)
    lesson_filter = ""
    lesson_params = []
    if user_id:
        lesson_filter += " AND ma.user_id=?"
        lesson_params.append(str(user_id))
    if scenario_id:
        lesson_filter += " AND ml.scenario_id=?"
        lesson_params.append(str(scenario_id))

    activity_cte = f"""
    WITH Activity AS (
      SELECT CONCAT('session-',CONVERT(NVARCHAR(36),s.id)) AS id,
             CASE WHEN s.status='completed' THEN 'session_completed' ELSE 'session_activity' END AS type,
             COALESCE(u.display_name,u.email) AS displayName,
             COALESCE(sc.title,'Sesión de práctica') AS title,
             COALESCE(s.finished_at,s.updated_at,s.created_at) AS occurredAt
      FROM dbo.session s
      JOIN dbo.app_user u ON u.id=s.user_id AND u.client_id=s.client_id
      LEFT JOIN dbo.scenario sc ON sc.id=s.scenario_id AND sc.client_id=s.client_id
      WHERE s.client_id=? AND ISNULL(s.is_deleted,0)=0
        AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
        {session_filter}
      UNION ALL
      SELECT CONCAT('lesson-',CONVERT(NVARCHAR(36),ma.id)),
             CASE WHEN ma.status='completed' THEN 'microlesson_completed' ELSE 'microlesson_started' END,
             COALESCE(u.display_name,u.email),ml.title,
             COALESCE(ma.completed_at,ma.started_at,ma.updated_at)
      FROM dbo.microlesson_assignment ma
      JOIN dbo.app_user u ON u.id=ma.user_id AND u.client_id=ma.client_id
      JOIN dbo.microlesson ml ON ml.id=ma.microlesson_id AND ml.client_id=ma.client_id
      WHERE ma.client_id=? AND ma.status IN ('in_progress','completed')
        AND COALESCE(ma.completed_at,ma.started_at,ma.updated_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
        {lesson_filter}
    )
    """
    base_params = [client_id, days, *session_params, client_id, days, *lesson_params]
    search = query.strip()
    search_sql = " WHERE (?='' OR displayName LIKE ? OR title LIKE ?)"
    search_params = [search, f"%{search}%", f"%{search}%"]

    cursor.execute(
        activity_cte + "/* client_usage_recent_count */ SELECT COUNT_BIG(*) FROM Activity" + search_sql,
        *base_params,
        *search_params,
    )
    count_row = cursor.fetchone()
    total = int(count_row[0]) if count_row else 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(page, total_pages)

    cursor.execute(
        activity_cte + """/* client_usage_recent_page */
        SELECT id,type,displayName,title,occurredAt FROM Activity""" + search_sql + """
        ORDER BY occurredAt DESC,id
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
        *base_params,
        *search_params,
        (safe_page - 1) * page_size,
        page_size,
    )
    items = _rows(cursor)
    for item in items:
        item["occurredAt"] = _iso(item["occurredAt"])
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "pageSize": page_size,
        "totalPages": total_pages,
    }


def get_spokesperson_detail(cursor, client_id, spokesperson_id, *, days=30):
    """Return the read-only overview for one spokesperson in the same client."""
    client_id = str(client_id)
    spokesperson_id = str(spokesperson_id)
    person = _spokesperson(cursor, client_id, spokesperson_id)
    usage = get_usage(cursor, client_id, days=days, user_id=spokesperson_id)

    cursor.execute(
        """/* client_spokesperson_detail_activity */
        SELECT MAX(activityAt)
        FROM (
          SELECT COALESCE(s.finished_at,s.updated_at,s.created_at) AS activityAt
          FROM dbo.session s
          WHERE s.client_id=? AND s.user_id=? AND ISNULL(s.is_deleted,0)=0
          UNION ALL
          SELECT COALESCE(ma.completed_at,ma.started_at,ma.updated_at,ma.assigned_at)
          FROM dbo.microlesson_assignment ma
          WHERE ma.client_id=? AND ma.user_id=? AND ma.status IN ('in_progress','completed')
        ) activity""",
        client_id,
        spokesperson_id,
        client_id,
        spokesperson_id,
    )
    activity_row = cursor.fetchone()
    last_activity = activity_row[0] if activity_row else None

    cursor.execute(
        """/* client_spokesperson_detail_lessons */
        SELECT
          SUM(CASE WHEN status='completed'
            AND COALESCE(completed_at,updated_at)>=DATEADD(DAY,-?,SYSUTCDATETIME()) THEN 1 ELSE 0 END),
          SUM(CASE WHEN status IN ('assigned','in_progress') THEN 1 ELSE 0 END)
        FROM dbo.microlesson_assignment
        WHERE client_id=? AND user_id=?""",
        days,
        client_id,
        spokesperson_id,
    )
    lessons_row = cursor.fetchone() or (0, 0)
    completed_lessons = int(lessons_row[0] or 0)
    pending_lessons = int(lessons_row[1] or 0)

    cursor.execute(
        """/* client_spokesperson_detail_alerts */
        SELECT
          SUM(CASE WHEN status IN ('failed','cancelled')
            AND COALESCE(finished_at,updated_at,created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME()) THEN 1 ELSE 0 END)
        FROM dbo.session
        WHERE client_id=? AND user_id=? AND ISNULL(is_deleted,0)=0""",
        days,
        client_id,
        spokesperson_id,
    )
    abandoned_row = cursor.fetchone()
    abandoned = int(abandoned_row[0] or 0) if abandoned_row else 0

    cursor.execute(
        """/* client_spokesperson_detail_unused_scenarios */
        SELECT COUNT_BIG(*)
        FROM dbo.scenario sc
        WHERE sc.client_id=? AND sc.status='active' AND ISNULL(sc.is_deleted,0)=0
          AND NOT EXISTS (
            SELECT 1 FROM dbo.session s
            WHERE s.client_id=sc.client_id AND s.scenario_id=sc.id AND s.user_id=?
              AND ISNULL(s.is_deleted,0)=0
              AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
          )""",
        client_id,
        spokesperson_id,
        days,
    )
    unused_row = cursor.fetchone()
    unused_scenarios = int(unused_row[0]) if unused_row else 0

    now = datetime.now(timezone.utc)
    if last_activity is None:
        participation_status = "not_started"
        inactive_days = None
    else:
        aware = last_activity.replace(tzinfo=timezone.utc) if last_activity.tzinfo is None else last_activity
        inactive_days = max(0, (now - aware.astimezone(timezone.utc)).days)
        if inactive_days <= 14:
            participation_status = "active"
        elif inactive_days <= 30:
            participation_status = "low_activity"
        else:
            participation_status = "inactive"

    alerts = []
    if participation_status == "not_started":
        alerts.append({"type": "not_started", "severity": "warning", "message": "Este vocero todavía no ha comenzado a utilizar la plataforma."})
    elif participation_status == "inactive":
        alerts.append({"type": "inactive", "severity": "warning", "message": f"No registra actividad hace {inactive_days} días."})
    if abandoned >= 2:
        alerts.append({"type": "abandoned_sessions", "severity": "attention", "message": f"Registra {abandoned} sesiones abandonadas en este período."})
    if pending_lessons:
        lesson_word = "microlección" if pending_lessons == 1 else "microlecciones"
        pending_word = "pendiente" if pending_lessons == 1 else "pendientes"
        alerts.append({"type": "pending_lessons", "severity": "info", "message": f"Tiene {pending_lessons} {lesson_word} {pending_word}."})
    if unused_scenarios:
        alerts.append({"type": "unused_scenarios", "severity": "info", "message": f"Hay {unused_scenarios} escenario{'s' if unused_scenarios != 1 else ''} activo{'s' if unused_scenarios != 1 else ''} sin practicar en este período."})

    return {
        "spokesperson": {
            **person,
            "lastActivityAt": _iso(last_activity),
            "participationStatus": participation_status,
            "inactiveDays": inactive_days,
        },
        "periodDays": days,
        "summary": {
            "completedSessions": usage["summary"]["completedSessions"],
            "trainingSeconds": usage["summary"]["trainingSeconds"],
            "scenariosUsed": len(usage["scenarios"]),
            "completedMicrolessons": completed_lessons,
        },
        "statusBreakdown": usage["statusBreakdown"],
        "trend": usage["trend"],
        "scenarios": usage["scenarios"],
        "alerts": alerts,
    }


def get_spokesperson_sessions(
    cursor,
    client_id,
    spokesperson_id,
    *,
    days=30,
    status="all",
    scenario_id=None,
    query="",
    page=1,
    page_size=5,
):
    """Return a sanitized, paginated session history for one spokesperson."""
    client_id = str(client_id)
    spokesperson_id = str(spokesperson_id)
    _spokesperson(cursor, client_id, spokesperson_id)
    normalized_status = "CASE WHEN s.status='completed' THEN 'completed' WHEN s.status IN ('failed','cancelled') THEN 'abandoned' ELSE 'in_progress' END"
    status_sql = f" AND {normalized_status}=?" if status != "all" else ""
    scenario_sql = " AND s.scenario_id=?" if scenario_id else ""
    search = query.strip()
    params = [client_id, spokesperson_id, days]
    if status != "all":
        params.append(status)
    if scenario_id:
        params.append(str(scenario_id))
    params.extend([search, f"%{search}%"])
    where = f"""
      FROM dbo.session s
      LEFT JOIN dbo.scenario sc ON sc.id=s.scenario_id AND sc.client_id=s.client_id
      OUTER APPLY (
        SELECT TOP 1 TRY_CONVERT(DECIMAL(12,3),COALESCE(
          JSON_VALUE(apr.summary_json,'$.metrics.audio.duracionSegundos'),
          JSON_VALUE(apr.summary_json,'$.metrics.audio.duracion_segundos')
        )) AS durationSeconds
        FROM dbo.analysis_job aj
        JOIN dbo.analysis_pipeline_result apr ON apr.analysis_job_id=aj.id
        WHERE aj.session_id=s.id AND apr.pipeline='fusion' AND ISJSON(apr.summary_json)=1
        ORDER BY apr.created_at DESC,apr.id DESC
      ) media
      WHERE s.client_id=? AND s.user_id=? AND ISNULL(s.is_deleted,0)=0
        AND COALESCE(s.finished_at,s.updated_at,s.created_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
        {status_sql}{scenario_sql}
        AND (?='' OR COALESCE(sc.title,'Sesión de práctica') LIKE ?)
    """
    cursor.execute("/* client_spokesperson_sessions_count */ SELECT COUNT_BIG(*)" + where, *params)
    count_row = cursor.fetchone()
    total = int(count_row[0]) if count_row else 0
    safe_page, total_pages, offset = _page(total, page, page_size)
    cursor.execute(
        f"""/* client_spokesperson_sessions_page */
        SELECT s.id,sc.id AS scenarioId,COALESCE(sc.title,'Sesión de práctica') AS scenarioTitle,
               {normalized_status} AS status,
               COALESCE(s.finished_at,s.updated_at,s.created_at) AS activityAt,
               media.durationSeconds
        {where}
        ORDER BY activityAt DESC,s.id
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
        *params,
        offset,
        page_size,
    )
    items = _rows(cursor)
    for item in items:
        item["id"] = str(item["id"])
        item["scenarioId"] = str(item["scenarioId"]) if item["scenarioId"] else None
        item["activityAt"] = _iso(item["activityAt"])
        item["durationSeconds"] = (
            max(0, round(float(item["durationSeconds"]), 1))
            if item["durationSeconds"] is not None else None
        )
    return {"items": items, "total": total, "page": safe_page, "pageSize": page_size, "totalPages": total_pages}


def get_spokesperson_microlessons(
    cursor,
    client_id,
    spokesperson_id,
    *,
    days=30,
    status="all",
    query="",
    page=1,
    page_size=5,
):
    """Return assignment metadata only; lesson contents remain private."""
    client_id = str(client_id)
    spokesperson_id = str(spokesperson_id)
    _spokesperson(cursor, client_id, spokesperson_id)
    status_sql = " AND ma.status=?" if status != "all" else ""
    search = query.strip()
    params = [client_id, spokesperson_id, days]
    if status != "all":
        params.append(status)
    params.extend([search, f"%{search}%", f"%{search}%"])
    where = f"""
      FROM dbo.microlesson_assignment ma
      JOIN dbo.microlesson ml ON ml.id=ma.microlesson_id AND ml.client_id=ma.client_id
      LEFT JOIN dbo.scenario sc ON sc.id=ml.scenario_id AND sc.client_id=ml.client_id
      WHERE ma.client_id=? AND ma.user_id=?
        AND COALESCE(ma.completed_at,ma.started_at,ma.updated_at,ma.assigned_at)>=DATEADD(DAY,-?,SYSUTCDATETIME())
        {status_sql}
        AND (?='' OR ml.title LIKE ? OR COALESCE(sc.title,'') LIKE ?)
    """
    cursor.execute("/* client_spokesperson_lessons_count */ SELECT COUNT_BIG(*)" + where, *params)
    count_row = cursor.fetchone()
    total = int(count_row[0]) if count_row else 0
    safe_page, total_pages, offset = _page(total, page, page_size)
    cursor.execute(
        """/* client_spokesperson_lessons_page */
        SELECT ma.id AS assignmentId,ml.id,ml.title,COALESCE(sc.title,'Sin escenario') AS scenarioTitle,
               ma.status,ml.duration_minutes AS durationMinutes,ma.assigned_at AS assignedAt,
               ma.started_at AS startedAt,ma.completed_at AS completedAt
        """ + where + """
        ORDER BY COALESCE(ma.completed_at,ma.started_at,ma.updated_at,ma.assigned_at) DESC,ma.id
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
        *params,
        offset,
        page_size,
    )
    items = _rows(cursor)
    for item in items:
        item["assignmentId"] = str(item["assignmentId"])
        item["id"] = str(item["id"])
        item["durationMinutes"] = int(item["durationMinutes"] or 0)
        item["assignedAt"] = _iso(item["assignedAt"])
        item["startedAt"] = _iso(item["startedAt"])
        item["completedAt"] = _iso(item["completedAt"])
    return {"items": items, "total": total, "page": safe_page, "pageSize": page_size, "totalPages": total_pages}
