"""Catálogo por empresa y sesiones persistentes; conserva el contrato público."""
from datetime import datetime, timezone
import hashlib
import uuid

from fastapi import HTTPException
import master_topics as store

SESSION_SCHEMA_DDL = """
IF COL_LENGTH('dbo.session', 'external_session_id') IS NULL
    ALTER TABLE dbo.session ADD external_session_id NVARCHAR(150) NULL;
IF COL_LENGTH('dbo.session', 'idempotency_key') IS NULL
    ALTER TABLE dbo.session ADD idempotency_key NVARCHAR(150) NULL;
IF COL_LENGTH('dbo.session_question', 'question_text') IS NULL
    ALTER TABLE dbo.session_question ADD question_text NVARCHAR(500) NULL;
"""
SESSION_INDEX_DDL = """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.session') AND name='UQ_session_external_id')
    CREATE UNIQUE INDEX UQ_session_external_id ON dbo.session(external_session_id) WHERE external_session_id IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.session') AND name='UQ_session_idempotency')
    CREATE UNIQUE INDEX UQ_session_idempotency ON dbo.session(user_id,idempotency_key) WHERE idempotency_key IS NOT NULL;
"""


def scenario_uuid(value):
    # Compatibilidad con los accesos rápidos anteriores; la autorización se
    # evalúa sobre el escenario real y el cliente, incluso para estos alias.
    aliases = {'crisis-voceria-01': 'topic-1', 'crisis-operativa-02': 'topic-2', 'crisis-reputacional-03': 'topic-3'}
    if value in aliases:
        return str(uuid.uuid5(uuid.UUID('f126b3bf-f626-47cd-9990-ae2b533c32eb'), aliases[value] + '/scenario'))
    return store.uid(value)


def visible_scenarios(cursor, profile, scenario_id=None):
    sql = """SELECT s.id,s.title,t.context,s.category,t.audience,s.difficulty,
             s.estimated_minutes AS estimatedMinutes,s.question_count AS questionCount
             FROM dbo.scenario s JOIN dbo.topic t ON t.id=s.topic_id
             JOIN dbo.client c ON c.id=s.client_id
             WHERE s.client_id=? AND s.status='active' AND t.status='active'
             AND s.is_deleted=0 AND t.is_deleted=0 AND c.status='active' AND c.is_deleted=0"""
    params = [profile['client_id']]
    if scenario_id:
        sql += ' AND s.id=?'
        params.append(scenario_uuid(scenario_id))
    sql += ' ORDER BY s.created_at DESC,s.id'
    cursor.execute(sql, tuple(params))
    result = store.rows(cursor)
    for scenario in result:
        scenario['id'] = str(scenario['id'])
        scenario['languages'] = ['es']
    return result


def list_catalog(connection_string, claims, category='', query='', page=1, page_size=20):
    with store.database(connection_string) as cursor:
        profile = store.resolve_user(cursor, claims)
        items = visible_scenarios(cursor, profile)
        if category:
            items = [s for s in items if s['category'] == category]
        if query:
            items = [s for s in items if query.casefold() in s['title'].casefold() or query.casefold() in s['context'].casefold()]
        total = len(items)
        return {'items': items[(page - 1) * page_size:page * page_size], 'page': page, 'pageSize': page_size, 'total': total}


def scenario_detail(connection_string, claims, scenario_id):
    with store.database(connection_string) as cursor:
        profile = store.resolve_user(cursor, claims)
        scenarios = visible_scenarios(cursor, profile, scenario_id)
        if not scenarios:
            raise HTTPException(404, 'Escenario no disponible para tu empresa.')
        return scenarios[0]


def owned_session(cursor, profile, session_id):
    try:
        internal_id = str(uuid.UUID(session_id))
    except ValueError:
        internal_id = None
    cursor.execute("""SELECT id,scenario_id,status,external_session_id FROM dbo.session
                      WHERE (external_session_id=? OR id=?) AND user_id=? AND client_id=? AND is_deleted=0""",
                   session_id, internal_id, profile['id'], profile['client_id'])
    session = cursor.fetchone()
    if session is None:
        raise HTTPException(404, 'Sesión no encontrada.')
    return session


def session_response(cursor, session):
    cursor.execute("SELECT COUNT(*) FROM dbo.session_question WHERE session_id=?", session[0])
    return {'sessionId': session[3] or str(session[0]), 'session_id': session[3] or str(session[0]),
            'scenarioId': str(session[1]), 'scenario_id': str(session[1]), 'status': session[2], 'questionCount': cursor.fetchone()[0]}


def create_session(connection_string, claims, scenario_id, language, idempotency_key=None):
    if language not in ('es', 'en', 'pt'):
        raise HTTPException(422, 'Idioma no válido.')
    if idempotency_key and len(idempotency_key) > 150:
        raise HTTPException(422, 'La clave de idempotencia es demasiado larga.')
    scenario_id = scenario_uuid(scenario_id)
    with store.database(connection_string) as cursor:
        profile = store.resolve_user(cursor, claims)
        cursor.execute('IF @@TRANCOUNT=0 BEGIN TRANSACTION;')
        if idempotency_key:
            resource = hashlib.sha256((profile['id'] + ':' + idempotency_key).encode()).hexdigest()
            cursor.execute("""DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=15000;
                              IF @r<0 THROW 51000,'No se pudo bloquear la creación de sesión',1;""", resource)
            cursor.execute('SELECT id,scenario_id,status,external_session_id,language FROM dbo.session WHERE user_id=? AND idempotency_key=? AND is_deleted=0', profile['id'], idempotency_key)
            existing = cursor.fetchone()
            if existing:
                if str(existing[1]).lower() != scenario_id or existing[4] != language:
                    raise HTTPException(409, 'La clave de idempotencia ya pertenece a otra solicitud.')
                return session_response(cursor, existing)
        # Bloquear primero el tema, igual que la edición maestra, para evitar
        # mezclar dos órdenes de preguntas o iniciar durante un archivado.
        cursor.execute('SELECT topic_id FROM dbo.scenario WHERE id=? AND client_id=?', scenario_id, profile['client_id'])
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, 'Escenario no disponible para tu empresa.')
        cursor.execute('SELECT id FROM dbo.topic WITH (UPDLOCK,HOLDLOCK) WHERE id=?', row[0])
        if not visible_scenarios(cursor, profile, scenario_id):
            raise HTTPException(404, 'Escenario no disponible para tu empresa.')
        cursor.execute("""SELECT q.id,sq.sequence_no,q.text FROM dbo.scenario_question sq
                          JOIN dbo.question q ON q.id=sq.question_id
                          WHERE sq.scenario_id=? AND sq.status='active' ORDER BY sq.sequence_no""", scenario_id)
        questions = cursor.fetchall()
        if not questions:
            raise HTTPException(409, 'Este escenario todavía no tiene preguntas configuradas.')
        cursor.execute("SELECT TOP 1 id FROM dbo.rubric_version WHERE status='published' ORDER BY published_at DESC,created_at DESC")
        rubric = cursor.fetchone()
        if not rubric:
            raise HTTPException(409, 'No hay una rúbrica publicada para iniciar la sesión.')
        internal_id = str(uuid.uuid4())
        public_id = f'session-{scenario_id}-{int(datetime.now(timezone.utc).timestamp())}'
        cursor.execute('SELECT id FROM dbo.session WHERE external_session_id=?', public_id)
        if cursor.fetchone():
            public_id += '-' + internal_id[:8]
        cursor.execute("""INSERT INTO dbo.session(id,user_id,client_id,scenario_id,language,status,rubric_version_id,external_session_id,idempotency_key)
                          VALUES(?,?,?,?,?,'created',?,?,?)""", internal_id, profile['id'], profile['client_id'], scenario_id, language, rubric[0], public_id, idempotency_key)
        for question in questions:
            cursor.execute('INSERT INTO dbo.session_question(id,session_id,question_id,sequence_no,question_text) VALUES(NEWID(),?,?,?,?)', internal_id, question[0], question[1], question[2])
        return {'sessionId': public_id, 'session_id': public_id, 'scenarioId': scenario_id, 'scenario_id': scenario_id, 'status': 'created', 'questionCount': len(questions)}


def get_session(connection_string, claims, session_id):
    with store.database(connection_string) as cursor:
        profile = store.resolve_user(cursor, claims)
        session = owned_session(cursor, profile, session_id)
        cursor.execute("""SELECT q.id,sq.sequence_no AS sequenceNo,COALESCE(sq.question_text,q.text) AS text
                          FROM dbo.session_question sq JOIN dbo.question q ON q.id=sq.question_id
                          WHERE sq.session_id=? ORDER BY sq.sequence_no""", session[0])
        questions = store.rows(cursor)
        if not questions:
            cursor.execute("""SELECT q.id,sq.sequence_no AS sequenceNo,q.text FROM dbo.scenario_question sq
                              JOIN dbo.question q ON q.id=sq.question_id WHERE sq.scenario_id=? AND sq.status='active' ORDER BY sq.sequence_no""", session[1])
            questions = store.rows(cursor)
        for question in questions:
            question['id'] = str(question['id'])
        cursor.execute('SELECT TOP 1 version_label,keep,term_days FROM dbo.retention_policy WHERE client_id=? AND is_current=1 ORDER BY effective_from DESC', profile['client_id'])
        policy = cursor.fetchone()
        return {'sessionId': session[3] or str(session[0]), 'scenarioId': str(session[1]), 'status': session[2], 'questions': questions,
                'retentionPolicy': {'version': policy[0] if policy else '1.0', 'keep': policy[1] if policy else 'full_recording', 'termDays': policy[2] if policy else 30}}
