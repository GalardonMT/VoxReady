"""Persistencia de agenda e historial del vocero sobre Azure SQL."""
from calendar import monthrange
from datetime import date, datetime
import uuid

from fastapi import HTTPException

import master_topics as store
import spokesperson_store


def _as_date(value, field_name="fecha"):
    if isinstance(value, datetime):
        raise HTTPException(422, f"La {field_name} debe contener solo año, mes y día.")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise HTTPException(422, f"La {field_name} no es válida.") from None


def _twelve_month_limit(today):
    target_year = today.year + 1
    target_day = min(today.day, monthrange(target_year, today.month)[1])
    return date(target_year, today.month, target_day)


def _validate_schedulable_date(value, today=None):
    scheduled_date = _as_date(value)
    current_date = _as_date(today or date.today(), "fecha actual")
    if scheduled_date < current_date or scheduled_date > _twelve_month_limit(current_date):
        raise HTTPException(422, "La fecha debe ser desde hoy y hasta doce meses en el futuro.")
    return scheduled_date


def _spokesperson(cursor, claims):
    profile = store.resolve_user(cursor, claims)
    if profile["role"] != "spokesperson":
        raise HTTPException(403, "Esta función está disponible solo para el vocero.")
    return profile


def _iso(value):
    return value.isoformat() if value is not None else None


def _uuid_text(value):
    return str(uuid.UUID(str(value))) if value is not None else None


def _active_scenario(cursor, profile, scenario_id):
    scenario_id = store.uid(scenario_id)
    cursor.execute(
        "SELECT topic_id FROM dbo.scenario WHERE id=? AND client_id=?",
        scenario_id,
        profile["client_id"],
    )
    topic = cursor.fetchone()
    if topic is None:
        raise HTTPException(404, "Escenario no disponible para tu empresa.")
    cursor.execute(
        "SELECT id FROM dbo.topic WITH (UPDLOCK,HOLDLOCK) WHERE id=?",
        topic[0],
    )
    if cursor.fetchone() is None:
        raise HTTPException(404, "Escenario no disponible para tu empresa.")
    cursor.execute(
        """SELECT s.id,s.title
           FROM dbo.scenario s WITH (UPDLOCK,HOLDLOCK)
           JOIN dbo.topic t ON t.id=s.topic_id
           JOIN dbo.client c ON c.id=s.client_id
           WHERE s.id=? AND s.client_id=? AND s.status='active'
             AND t.status='active' AND c.status='active'
             AND s.is_deleted=0 AND t.is_deleted=0 AND c.is_deleted=0""",
        scenario_id,
        profile["client_id"],
    )
    row = cursor.fetchone()
    if row is None:
        # El mismo resultado cubre escenario ajeno, archivado o inexistente.
        raise HTTPException(404, "Escenario no disponible para tu empresa.")
    return str(row[0]), row[1]


def _scenario_payload(scenario_id, title, status, scenario_deleted, topic_status, topic_deleted):
    if scenario_id is None:
        return None
    available = (
        status == "active"
        and not bool(scenario_deleted)
        and topic_status == "active"
        and not bool(topic_deleted)
    )
    return {
        "id": _uuid_text(scenario_id),
        "title": title or "Escenario no disponible",
        "status": status or "archived",
        "available": available,
    }


def _schedule_response(row):
    session_id = row[4]
    external_session_id = row[5]
    return {
        "id": _uuid_text(row[0]),
        "date": _iso(row[1]),
        "status": row[2],
        "scenario": _scenario_payload(row[3], row[8], row[9], row[10], row[11], row[12]),
        "sessionId": external_session_id or _uuid_text(session_id),
        "createdAt": _iso(row[6]),
        "updatedAt": _iso(row[7]),
    }


def _owned_schedule(cursor, profile, schedule_id, *, lock=False):
    try:
        schedule_id = str(uuid.UUID(str(schedule_id)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(404, "Agenda no encontrada.") from None
    hint = " WITH (UPDLOCK,HOLDLOCK)" if lock else ""
    cursor.execute(
        """SELECT sch.id,sch.scheduled_date,sch.status,sch.scenario_id,sch.session_id,
                  sc.title,sc.status,sc.is_deleted,t.status,t.is_deleted
           FROM dbo.schedule sch"""
        + hint
        + """
           LEFT JOIN dbo.scenario sc ON sc.id=sch.scenario_id AND sc.client_id=sch.client_id
           LEFT JOIN dbo.topic t ON t.id=sc.topic_id
           WHERE sch.id=? AND sch.user_id=? AND sch.client_id=?""",
        schedule_id,
        profile["id"],
        profile["client_id"],
    )
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Agenda no encontrada.")
    return row


def list_calendar(connection_string, claims, date_from, date_to):
    """Lista agenda visible e historial completado dentro de un rango inclusivo."""
    date_from = _as_date(date_from, "fecha inicial")
    date_to = _as_date(date_to, "fecha final")
    if date_from > date_to:
        raise HTTPException(422, "La fecha inicial no puede ser posterior a la fecha final.")
    if (date_to - date_from).days > 365:
        raise HTTPException(422, "El rango del calendario no puede superar 366 días.")

    with store.database(connection_string) as cursor:
        profile = _spokesperson(cursor, claims)
        cursor.execute(
            """SELECT sch.id,sch.scheduled_date,sch.status,sch.scenario_id,sch.session_id,
                      sess.external_session_id,sch.created_at,sch.updated_at,
                      sc.title,sc.status,sc.is_deleted,t.status,t.is_deleted
               FROM dbo.schedule sch
               LEFT JOIN dbo.scenario sc ON sc.id=sch.scenario_id AND sc.client_id=sch.client_id
               LEFT JOIN dbo.topic t ON t.id=sc.topic_id
               LEFT JOIN dbo.session sess ON sess.id=sch.session_id
                    AND sess.user_id=sch.user_id AND sess.client_id=sch.client_id
                    AND sess.is_deleted=0
               WHERE sch.user_id=? AND sch.client_id=?
                 AND sch.scheduled_date BETWEEN ? AND ?
                 AND sch.status IN ('scheduled','completed')
               ORDER BY sch.scheduled_date,sch.created_at,sch.id""",
            profile["id"],
            profile["client_id"],
            date_from,
            date_to,
        )
        schedules = [_schedule_response(row) for row in cursor.fetchall()]

        cursor.execute(
            """WITH CurrentReports AS (
                   SELECT r.id,r.session_id,r.overall_score,r.generated_at,
                          ROW_NUMBER() OVER (
                              PARTITION BY r.session_id
                              ORDER BY r.generated_at DESC,r.id DESC
                          ) AS report_rank
                   FROM dbo.report r
                   WHERE r.is_current=1
               ), RankedAreaScores AS (
                   SELECT a.report_id,ra.area_key,a.value,
                          ROW_NUMBER() OVER (
                              PARTITION BY a.report_id,ra.area_key
                              ORDER BY a.id DESC
                          ) AS area_rank
                   FROM dbo.area_score a
                   JOIN dbo.rubric_area ra ON ra.id=a.rubric_area_id
               )
               SELECT s.id,s.external_session_id,s.finished_at,s.scenario_id,sc.title,
                      r.id,r.overall_score,r.generated_at,a.area_key,a.value
               FROM dbo.session s
               JOIN dbo.scenario sc ON sc.id=s.scenario_id AND sc.client_id=s.client_id
               JOIN CurrentReports r ON r.session_id=s.id AND r.report_rank=1
               LEFT JOIN RankedAreaScores a ON a.report_id=r.id AND a.area_rank=1
               WHERE s.user_id=? AND s.client_id=? AND s.status='completed'
                 AND s.is_deleted=0
                 AND CAST(COALESCE(s.finished_at,r.generated_at,s.updated_at) AS date) BETWEEN ? AND ?
               ORDER BY COALESCE(s.finished_at,r.generated_at,s.updated_at),s.id,a.area_key""",
            profile["id"],
            profile["client_id"],
            date_from,
            date_to,
        )
        sessions = []
        by_session = {}
        for row in cursor.fetchall():
            key = str(row[0])
            item = by_session.get(key)
            if item is None:
                completed_at = row[2] or row[7]
                item = {
                    "sessionId": row[1] or key,
                    "date": _iso(completed_at.date()),
                    "completedAt": _iso(completed_at),
                    "scenario": {"id": _uuid_text(row[3]), "title": row[4]},
                    "report": {
                        "id": _uuid_text(row[5]),
                        "overallScore": row[6],
                        "generatedAt": _iso(row[7]),
                        "areas": [],
                    },
                }
                by_session[key] = item
                sessions.append(item)
            if row[8] is not None:
                item["report"]["areas"].append({"key": row[8], "value": row[9]})

        return {
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "schedules": schedules,
            "sessions": sessions,
        }


def create_schedule(connection_string, claims, scheduled_date, scenario_id, *, today=None):
    scheduled_date = _validate_schedulable_date(scheduled_date, today)
    with store.database(connection_string) as cursor:
        profile = _spokesperson(cursor, claims)
        scenario_id, scenario_title = _active_scenario(cursor, profile, scenario_id)
        schedule_id = str(uuid.uuid4())
        cursor.execute(
            """INSERT INTO dbo.schedule
                      (id,client_id,user_id,scheduled_date,scenario_id,status,created_at,updated_at)
               VALUES(?,?,?,?,?,'scheduled',SYSUTCDATETIME(),SYSUTCDATETIME())""",
            schedule_id,
            profile["client_id"],
            profile["id"],
            scheduled_date,
            scenario_id,
        )
        return {
            "id": schedule_id,
            "date": scheduled_date.isoformat(),
            "status": "scheduled",
            "scenario": {
                "id": scenario_id,
                "title": scenario_title,
                "status": "active",
                "available": True,
            },
            "sessionId": None,
        }


def update_schedule(
    connection_string,
    claims,
    schedule_id,
    *,
    scheduled_date=None,
    scenario_id=None,
    today=None,
):
    if scheduled_date is None and scenario_id is None:
        raise HTTPException(422, "Debes indicar una nueva fecha o un escenario.")
    if scheduled_date is not None:
        scheduled_date = _validate_schedulable_date(scheduled_date, today)

    with store.database(connection_string) as cursor:
        profile = _spokesperson(cursor, claims)
        selected_scenario = None
        if scenario_id is not None:
            selected_scenario = _active_scenario(cursor, profile, scenario_id)
        current = _owned_schedule(cursor, profile, schedule_id, lock=True)
        if current[2] != "scheduled" or current[4] is not None:
            raise HTTPException(409, "Solo puedes editar una agenda pendiente y aún no iniciada.")

        next_date = scheduled_date or current[1]
        next_scenario_id = str(current[3])
        scenario_title = current[5]
        scenario_status = current[6]
        scenario_deleted = current[7]
        topic_status = current[8]
        topic_deleted = current[9]
        if selected_scenario is not None:
            next_scenario_id, scenario_title = selected_scenario
            scenario_status = "active"
            scenario_deleted = 0
            topic_status = "active"
            topic_deleted = 0

        cursor.execute(
            """UPDATE dbo.schedule
               SET scheduled_date=?,scenario_id=?,updated_at=SYSUTCDATETIME()
               WHERE id=? AND user_id=? AND client_id=?
                 AND status='scheduled' AND session_id IS NULL""",
            next_date,
            next_scenario_id,
            _uuid_text(current[0]),
            profile["id"],
            profile["client_id"],
        )
        return {
            "id": _uuid_text(current[0]),
            "date": next_date.isoformat(),
            "status": "scheduled",
            "scenario": _scenario_payload(
                next_scenario_id,
                scenario_title,
                scenario_status,
                scenario_deleted,
                topic_status,
                topic_deleted,
            ),
            "sessionId": None,
        }


def cancel_schedule(connection_string, claims, schedule_id):
    with store.database(connection_string) as cursor:
        profile = _spokesperson(cursor, claims)
        current = _owned_schedule(cursor, profile, schedule_id, lock=True)
        if current[2] != "scheduled" or current[4] is not None:
            raise HTTPException(409, "Solo puedes cancelar una agenda pendiente y aún no iniciada.")
        cursor.execute(
            """UPDATE dbo.schedule SET status='cancelled',updated_at=SYSUTCDATETIME()
               WHERE id=? AND user_id=? AND client_id=?
                 AND status='scheduled' AND session_id IS NULL""",
            _uuid_text(current[0]),
            profile["id"],
            profile["client_id"],
        )
        return {"id": _uuid_text(current[0]), "status": "cancelled"}


def start_schedule(connection_string, claims, schedule_id):
    """Crea y vincula una sesión a una cita en una única transacción.

    El bloqueo de aplicación hace idempotentes los dobles clics. La
    actualización condicional evita vincular la sesión si la cita fue editada
    o cancelada mientras se preparaba la práctica.
    """
    try:
        schedule_id = str(uuid.UUID(str(schedule_id)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(404, "Agenda no encontrada.") from None

    with store.database(connection_string) as cursor:
        profile = _spokesperson(cursor, claims)
        cursor.execute("IF @@TRANCOUNT=0 BEGIN TRANSACTION;")
        cursor.execute(
            """DECLARE @r int;
               EXEC @r=sys.sp_getapplock
                    @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=15000;
               IF @r<0 THROW 51000,'No se pudo bloquear el inicio de la agenda',1;""",
            "voxready-schedule-start:" + schedule_id,
        )
        cursor.execute(
            """SELECT sch.id,sch.status,sch.scenario_id,sch.session_id,
                      sess.id,sess.scenario_id,sess.status,sess.external_session_id
               FROM dbo.schedule sch
               LEFT JOIN dbo.session sess ON sess.id=sch.session_id
                    AND sess.user_id=sch.user_id AND sess.client_id=sch.client_id
                    AND sess.is_deleted=0
               WHERE sch.id=? AND sch.user_id=? AND sch.client_id=?""",
            schedule_id,
            profile["id"],
            profile["client_id"],
        )
        scheduled = cursor.fetchone()
        if scheduled is None:
            raise HTTPException(404, "Agenda no encontrada.")

        if scheduled[3] is not None:
            if scheduled[4] is None:
                raise HTTPException(409, "La sesión vinculada a esta agenda no está disponible.")
            session = (scheduled[4], scheduled[5], scheduled[6], scheduled[7])
            response = spokesperson_store.session_response(cursor, session)
            response["scheduleId"] = schedule_id
            return response

        if scheduled[1] != "scheduled":
            raise HTTPException(409, "Solo puedes iniciar una agenda pendiente.")

        session_response, internal_session_id = spokesperson_store.create_session_in_transaction(
            cursor,
            profile,
            str(scheduled[2]),
            "es",
            "schedule:" + schedule_id,
        )
        cursor.execute(
            """UPDATE dbo.schedule
               SET session_id=?,updated_at=SYSUTCDATETIME()
               WHERE id=? AND user_id=? AND client_id=?
                 AND status='scheduled' AND session_id IS NULL AND scenario_id=?""",
            internal_session_id,
            schedule_id,
            profile["id"],
            profile["client_id"],
            str(scheduled[2]),
        )
        if cursor.rowcount != 1:
            raise HTTPException(409, "La agenda cambió mientras se iniciaba. Inténtalo nuevamente.")
        session_response["scheduleId"] = schedule_id
        return session_response
