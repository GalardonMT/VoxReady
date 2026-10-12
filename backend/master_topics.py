"""Persistencia SQL del catálogo maestro, aislada de autenticación y análisis."""
from contextlib import contextmanager
import logging
import uuid

import pyodbc
from fastapi import HTTPException

logger = logging.getLogger("uvicorn.error")

MASTER_SCHEMA_DDL = """
IF COL_LENGTH('dbo.question', 'sort_order') IS NULL
    ALTER TABLE dbo.question ADD sort_order INT NOT NULL CONSTRAINT DF_question_sort_order DEFAULT 0;
IF COL_LENGTH('dbo.topic_key_message', 'status') IS NULL
    ALTER TABLE dbo.topic_key_message ADD status NVARCHAR(20) NOT NULL CONSTRAINT DF_topic_key_message_status DEFAULT 'active';
IF COL_LENGTH('dbo.topic_red_line', 'status') IS NULL
    ALTER TABLE dbo.topic_red_line ADD status NVARCHAR(20) NOT NULL CONSTRAINT DF_topic_red_line_status DEFAULT 'active';
IF COL_LENGTH('dbo.scenario_question', 'status') IS NULL
    ALTER TABLE dbo.scenario_question ADD status NVARCHAR(20) NOT NULL CONSTRAINT DF_scenario_question_status DEFAULT 'active';
"""


@contextmanager
def database(connection_string):
    if not connection_string:
        raise HTTPException(503, "Azure SQL no está configurado.")
    conn = None
    try:
        if "DRIVER=" not in connection_string.upper():
            connection_string = "DRIVER={ODBC Driver 18 for SQL Server};" + connection_string
        conn = pyodbc.connect(connection_string, timeout=30, autocommit=False)
        conn.timeout = 30
        cursor = conn.cursor()
        cursor.execute("SET XACT_ABORT ON; SET LOCK_TIMEOUT 15000;")
        yield cursor
        conn.commit()
    except pyodbc.Error as error:
        if conn:
            conn.rollback()
        logger.error("Master topics SQL error: %s", error.args[0] if error.args else "unknown")
        raise HTTPException(503, "No se pudo completar la operación en Azure SQL.") from None
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def uid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(422, "Identificador UUID inválido.") from None


def rows(cursor):
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def resolve_user(cursor, claims, master=False):
    """El rol y cliente vienen de app_user, nunca del payload o de localStorage."""
    row = None
    identity = claims.get("oid") or claims.get("sub")
    try:
        identity = str(uuid.UUID(str(identity)))
    except (TypeError, ValueError, AttributeError):
        identity = None
    if identity:
        cursor.execute("SELECT id,client_id,role FROM dbo.app_user WHERE id=? AND (is_deleted IS NULL OR is_deleted=0)", identity)
        row = cursor.fetchone()
    email = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or claims.get("unique_name"))
    if not email and isinstance(claims.get("emails"), list) and claims["emails"]:
        email = claims["emails"][0]
    if row is None and email:
        cursor.execute("SELECT id,client_id,role FROM dbo.app_user WHERE LOWER(email)=LOWER(?) AND (is_deleted IS NULL OR is_deleted=0)", email)
        matches = cursor.fetchall()
        if len(matches) == 1:
            row = matches[0]
    if row is None:
        raise HTTPException(403, "Usuario no registrado en VoxReady.")
    profile = {"id": str(row[0]), "client_id": str(row[1]) if row[1] else None, "role": row[2]}
    if master and profile["role"] != "master_config":
        raise HTTPException(403, "Se requiere el rol master_config.")
    if not master and not profile["client_id"]:
        raise HTTPException(403, "El usuario no tiene una empresa asignada.")
    return profile


def require_topic(cursor, topic_id, lock=False):
    hint = " WITH (UPDLOCK,HOLDLOCK)" if lock else ""
    cursor.execute("SELECT id,status FROM dbo.topic" + hint + " WHERE id=? AND client_id IS NULL AND is_deleted=0", uid(topic_id))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Tema maestro no encontrado.")
    return row[1]


def scenario_topic(cursor, scenario_id):
    cursor.execute("SELECT s.topic_id FROM dbo.scenario s JOIN dbo.topic t ON t.id=s.topic_id WHERE s.id=? AND t.client_id IS NULL AND s.is_deleted=0 AND t.is_deleted=0", uid(scenario_id))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Escenario maestro no encontrado.")
    return str(row[0])


def scenarios_for_topic(cursor, topic_id):
    cursor.execute("""SELECT s.id,s.title,s.category,s.difficulty,s.estimated_minutes AS estimatedMinutes,
                      s.question_count AS questionCount,s.client_id AS clientId,c.name AS clientName,s.status
                      FROM dbo.scenario s JOIN dbo.client c ON c.id=s.client_id
                      WHERE s.topic_id=? AND s.is_deleted=0 ORDER BY s.created_at,s.id""", topic_id)
    result = rows(cursor)
    for scenario in result:
        scenario["id"] = str(scenario["id"])
        scenario["clientId"] = str(scenario["clientId"])
        cursor.execute("""SELECT q.id,q.text,sq.sequence_no AS sequenceNo,q.status
                          FROM dbo.scenario_question sq JOIN dbo.question q ON q.id=sq.question_id
                          WHERE sq.scenario_id=? AND sq.status='active' ORDER BY sq.sequence_no""", scenario["id"])
        scenario["questions"] = rows(cursor)
        for question in scenario["questions"]:
            question["id"] = str(question["id"])
        scenario["questionIds"] = [q["id"] for q in scenario["questions"]]
    return result


def topic_detail(cursor, topic_id):
    require_topic(cursor, topic_id)
    cursor.execute("SELECT id,name,context,optics,audience,status FROM dbo.topic WHERE id=?", topic_id)
    topic = rows(cursor)[0]
    topic["id"] = str(topic["id"])
    for table, field in (("topic_key_message", "keyMessages"), ("topic_red_line", "redLines")):
        cursor.execute(f"SELECT text FROM dbo.[{table}] WHERE topic_id=? AND status='active' ORDER BY sort_order,id", topic_id)
        topic[field] = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT id,text,sort_order AS sortOrder,status FROM dbo.question WHERE topic_id=? AND in_bank=1 AND status='active' AND is_deleted=0 ORDER BY sort_order,created_at,id", topic_id)
    topic["questions"] = rows(cursor)
    for question in topic["questions"]:
        question["id"] = str(question["id"])
    topic["scenarios"] = scenarios_for_topic(cursor, topic_id)
    return topic


def save_messages(cursor, topic_id, table, texts):
    cursor.execute(f"SELECT id FROM dbo.[{table}] WHERE topic_id=? AND status='active' ORDER BY sort_order,id", topic_id)
    old_ids = [r[0] for r in cursor.fetchall()]
    for index, text in enumerate(texts):
        if index < len(old_ids):
            cursor.execute(f"UPDATE dbo.[{table}] SET text=?,sort_order=? WHERE id=?", text, index + 1, old_ids[index])
        else:
            cursor.execute(f"INSERT INTO dbo.[{table}](id,topic_id,text,sort_order,status) VALUES(NEWID(),?,?,?,'active')", topic_id, text, index + 1)
    for old_id in old_ids[len(texts):]:
        cursor.execute(f"UPDATE dbo.[{table}] SET status='archived' WHERE id=?", old_id)


def save_questions(cursor, topic_id, questions):
    cursor.execute("SELECT id FROM dbo.question WHERE topic_id=? AND is_deleted=0", topic_id)
    existing = {str(row[0]).lower() for row in cursor.fetchall()}
    received = set()
    for position, question in enumerate(questions, 1):
        question_id = str(question.id).lower() if question.id else None
        if question_id:
            if question_id not in existing or question_id in received:
                raise HTTPException(422, "Pregunta duplicada o perteneciente a otro tema.")
            received.add(question_id)
            cursor.execute("UPDATE dbo.question SET text=?,sort_order=?,in_bank=1,status='active',updated_at=SYSUTCDATETIME() WHERE id=? AND topic_id=?", question.text, position, question_id, topic_id)
        else:
            cursor.execute("""INSERT INTO dbo.question(id,topic_id,client_id,text,sort_order,source,base_language,in_bank,status)
                              VALUES(NEWID(),?,NULL,?,?,'master','es',1,'active')""", topic_id, question.text, position)
    for removed in existing - received:
        cursor.execute("UPDATE dbo.question SET in_bank=0,status='archived',updated_at=SYSUTCDATETIME() WHERE id=?", removed)


def save_assignments(cursor, scenario_id, topic_id, question_ids):
    cursor.execute("SELECT question_id FROM dbo.scenario_question WHERE scenario_id=? AND status='active'", scenario_id)
    retained = {str(row[0]).lower() for row in cursor.fetchall()}
    for question_id in question_ids:
        cursor.execute("SELECT status,in_bank FROM dbo.question WHERE id=? AND topic_id=? AND is_deleted=0", question_id, topic_id)
        question = cursor.fetchone()
        if question is None or (question_id not in retained and (question[0] != "active" or not question[1])):
            raise HTTPException(422, "Selecciona preguntas del banco activo de este tema.")
    # Liberar posiciones sin eliminar relaciones. Todo el intervalo se mueve por
    # debajo de su mínimo anterior; nunca colisiona con posiciones activas 1..N.
    cursor.execute("SELECT MIN(sequence_no),MAX(sequence_no),COUNT(*) FROM dbo.scenario_question WHERE scenario_id=?", scenario_id)
    minimum, maximum, count = cursor.fetchone()
    if count:
        offset = max(maximum - minimum + count + 1, maximum + count + 1)
        if minimum - offset < -2147483648:
            raise HTTPException(409, "El escenario necesita ampliar el rango de secuencias antes de editarse.")
        cursor.execute("UPDATE dbo.scenario_question SET status='archived',sequence_no=sequence_no-? WHERE scenario_id=?", offset, scenario_id)
    for position, question_id in enumerate(question_ids, 1):
        cursor.execute("SELECT id FROM dbo.scenario_question WHERE scenario_id=? AND question_id=?", scenario_id, question_id)
        existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE dbo.scenario_question SET status='active',sequence_no=? WHERE id=?", position, existing[0])
        else:
            cursor.execute("INSERT INTO dbo.scenario_question(id,scenario_id,question_id,sequence_no,status) VALUES(NEWID(),?,?,?,'active')", scenario_id, question_id, position)


def save_scenario(cursor, topic_id, payload, scenario_id=None):
    topic_status = require_topic(cursor, topic_id, lock=True)
    if topic_status != "active":
        raise HTTPException(409, "Reactiva el tema antes de configurar sus escenarios.")
    client_id = str(payload.clientId)
    cursor.execute("SELECT id FROM dbo.client WHERE id=? AND status='active' AND is_deleted=0", client_id)
    if not cursor.fetchone():
        raise HTTPException(422, "Selecciona un cliente activo.")
    scenario_id = scenario_id or str(uuid.uuid4())
    cursor.execute("SELECT id FROM dbo.scenario WHERE id=?", scenario_id)
    if cursor.fetchone():
        cursor.execute("UPDATE dbo.scenario SET title=?,category=?,difficulty=?,estimated_minutes=?,client_id=?,question_count=?,updated_at=SYSUTCDATETIME() WHERE id=?", payload.title, payload.category, payload.difficulty, payload.estimatedMinutes, client_id, len(payload.questionIds), scenario_id)
    else:
        cursor.execute("INSERT INTO dbo.scenario(id,topic_id,client_id,title,category,difficulty,estimated_minutes,question_count,status) VALUES(?,?,?,?,?,?,?,?,'active')", scenario_id, topic_id, client_id, payload.title, payload.category, payload.difficulty, payload.estimatedMinutes, len(payload.questionIds))
    save_assignments(cursor, scenario_id, topic_id, [str(q).lower() for q in payload.questionIds])
    return next(s for s in scenarios_for_topic(cursor, topic_id) if s["id"].lower() == scenario_id.lower())
