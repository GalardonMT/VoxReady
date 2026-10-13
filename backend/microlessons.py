"""Persistencia y autorizacion de microlecciones sobre Azure SQL."""
from __future__ import annotations

import uuid

from fastapi import HTTPException

import master_topics as store


MICROLESSON_SCHEMA_DDL = """
IF OBJECT_ID(N'dbo.microlesson', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.microlesson (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_microlesson PRIMARY KEY,
        client_id UNIQUEIDENTIFIER NOT NULL,
        scenario_id UNIQUEIDENTIFIER NOT NULL,
        title NVARCHAR(150) NOT NULL,
        topic_tag NVARCHAR(50) NULL,
        duration_minutes INT NULL,
        learning_objective NVARCHAR(MAX) NOT NULL,
        theory_content NVARCHAR(MAX) NOT NULL,
        example_content NVARCHAR(MAX) NULL,
        video_blob_path NVARCHAR(400) NULL,
        video_file_name NVARCHAR(255) NULL,
        video_content_type NVARCHAR(100) NULL,
        video_size_bytes BIGINT NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_microlesson_status DEFAULT 'active',
        created_at DATETIME2 NOT NULL CONSTRAINT DF_microlesson_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_microlesson_updated_at DEFAULT SYSUTCDATETIME(),
        is_deleted BIT NOT NULL CONSTRAINT DF_microlesson_is_deleted DEFAULT 0,
        deleted_at DATETIME2 NULL,
        CONSTRAINT FK_microlesson_client FOREIGN KEY (client_id) REFERENCES dbo.client(id),
        CONSTRAINT FK_microlesson_scenario FOREIGN KEY (scenario_id) REFERENCES dbo.scenario(id),
        CONSTRAINT CK_microlesson_status CHECK (status IN ('active', 'archived')),
        CONSTRAINT CK_microlesson_duration CHECK (duration_minutes IS NULL OR duration_minutes > 0),
        CONSTRAINT CK_microlesson_video_size CHECK (video_size_bytes IS NULL OR video_size_bytes > 0)
    );
END;

IF COL_LENGTH('dbo.microlesson', 'client_id') IS NULL
    ALTER TABLE dbo.microlesson ADD client_id UNIQUEIDENTIFIER NULL;
IF COL_LENGTH('dbo.microlesson', 'scenario_id') IS NULL
    ALTER TABLE dbo.microlesson ADD scenario_id UNIQUEIDENTIFIER NULL;
IF COL_LENGTH('dbo.microlesson', 'title') IS NULL
    ALTER TABLE dbo.microlesson ADD title NVARCHAR(150) NULL;
IF COL_LENGTH('dbo.microlesson', 'topic_tag') IS NULL
    ALTER TABLE dbo.microlesson ADD topic_tag NVARCHAR(50) NULL;
IF COL_LENGTH('dbo.microlesson', 'duration_minutes') IS NULL
    ALTER TABLE dbo.microlesson ADD duration_minutes INT NULL;
IF COL_LENGTH('dbo.microlesson', 'video_blob_path') IS NULL
    ALTER TABLE dbo.microlesson ADD video_blob_path NVARCHAR(400) NULL;
IF COL_LENGTH('dbo.microlesson', 'example_content') IS NULL
    ALTER TABLE dbo.microlesson ADD example_content NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.microlesson', 'status') IS NULL
    ALTER TABLE dbo.microlesson ADD status NVARCHAR(20) NOT NULL CONSTRAINT DF_microlesson_status_migration DEFAULT 'active';
IF COL_LENGTH('dbo.microlesson', 'learning_objective') IS NULL
    ALTER TABLE dbo.microlesson ADD learning_objective NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.microlesson', 'theory_content') IS NULL
    ALTER TABLE dbo.microlesson ADD theory_content NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.microlesson', 'video_file_name') IS NULL
    ALTER TABLE dbo.microlesson ADD video_file_name NVARCHAR(255) NULL;
IF COL_LENGTH('dbo.microlesson', 'video_content_type') IS NULL
    ALTER TABLE dbo.microlesson ADD video_content_type NVARCHAR(100) NULL;
IF COL_LENGTH('dbo.microlesson', 'video_size_bytes') IS NULL
    ALTER TABLE dbo.microlesson ADD video_size_bytes BIGINT NULL;
IF COL_LENGTH('dbo.microlesson', 'is_deleted') IS NULL
    ALTER TABLE dbo.microlesson ADD is_deleted BIT NOT NULL CONSTRAINT DF_microlesson_is_deleted_migration DEFAULT 0;
IF COL_LENGTH('dbo.microlesson', 'deleted_at') IS NULL
    ALTER TABLE dbo.microlesson ADD deleted_at DATETIME2 NULL;
IF COL_LENGTH('dbo.microlesson', 'created_at') IS NULL
    ALTER TABLE dbo.microlesson ADD created_at DATETIME2 NOT NULL CONSTRAINT DF_microlesson_created_at_migration DEFAULT SYSUTCDATETIME();
IF COL_LENGTH('dbo.microlesson', 'updated_at') IS NULL
    ALTER TABLE dbo.microlesson ADD updated_at DATETIME2 NOT NULL CONSTRAINT DF_microlesson_updated_at_migration DEFAULT SYSUTCDATETIME();
"""

MICROLESSON_DATA_DDL = """
IF COL_LENGTH('dbo.microlesson', 'id') IS NULL
    THROW 51000, 'La tabla microlesson existente no tiene una clave id compatible.', 1;
IF EXISTS (SELECT 1 FROM dbo.microlesson WHERE id IS NULL)
    THROW 51000, 'Hay microlecciones existentes sin id.', 1;
IF EXISTS (SELECT 1 FROM dbo.microlesson WHERE client_id IS NULL)
    THROW 51000, 'Hay microlecciones existentes sin cliente; asignalas antes de continuar.', 1;
UPDATE dbo.microlesson SET title=N'Microleccion pendiente de actualizacion.' WHERE title IS NULL OR LTRIM(RTRIM(title))='';
UPDATE dbo.microlesson SET learning_objective=N'Contenido pendiente de actualizacion.'
WHERE learning_objective IS NULL;
UPDATE dbo.microlesson SET theory_content=N'Contenido pendiente de actualizacion.'
WHERE theory_content IS NULL;
UPDATE dbo.microlesson SET status='archived' WHERE status NOT IN ('active','archived') OR status IS NULL;
UPDATE dbo.microlesson SET is_deleted=0 WHERE is_deleted IS NULL;
UPDATE dbo.microlesson SET created_at=SYSUTCDATETIME() WHERE created_at IS NULL;
UPDATE dbo.microlesson SET updated_at=COALESCE(created_at,SYSUTCDATETIME()) WHERE updated_at IS NULL;

IF EXISTS (SELECT 1 FROM dbo.microlesson WHERE scenario_id IS NULL)
BEGIN
    UPDATE ml SET scenario_id=matches.id
    FROM dbo.microlesson ml
    CROSS APPLY (
        SELECT TOP 1 s.id FROM dbo.scenario s
        WHERE s.client_id=ml.client_id AND s.is_deleted=0 ORDER BY s.id
    ) matches
    WHERE ml.scenario_id IS NULL
      AND (SELECT COUNT(*) FROM dbo.scenario s WHERE s.client_id=ml.client_id AND s.is_deleted=0)=1;
END;
IF EXISTS (SELECT 1 FROM dbo.microlesson WHERE scenario_id IS NULL)
    THROW 51000, 'Hay microlecciones existentes sin escenario; asignalas antes de continuar.', 1;
"""

MICROLESSON_CONSTRAINT_DDL = """
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'id' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN id UNIQUEIDENTIFIER NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'client_id' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN client_id UNIQUEIDENTIFIER NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'scenario_id' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN scenario_id UNIQUEIDENTIFIER NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'title' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN title NVARCHAR(150) NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'learning_objective' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN learning_objective NVARCHAR(MAX) NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'theory_content' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN theory_content NVARCHAR(MAX) NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'is_deleted' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN is_deleted BIT NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'status' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN status NVARCHAR(20) NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'created_at' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN created_at DATETIME2 NOT NULL;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'updated_at' AND is_nullable=1)
    ALTER TABLE dbo.microlesson ALTER COLUMN updated_at DATETIME2 NOT NULL;

IF NOT EXISTS (SELECT 1 FROM sys.default_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.microlesson'),N'status','ColumnId'))
    ALTER TABLE dbo.microlesson ADD CONSTRAINT DF_microlesson_status_existing DEFAULT 'active' FOR status;
IF NOT EXISTS (SELECT 1 FROM sys.default_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.microlesson'),N'created_at','ColumnId'))
    ALTER TABLE dbo.microlesson ADD CONSTRAINT DF_microlesson_created_at_existing DEFAULT SYSUTCDATETIME() FOR created_at;
IF NOT EXISTS (SELECT 1 FROM sys.default_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.microlesson'),N'updated_at','ColumnId'))
    ALTER TABLE dbo.microlesson ADD CONSTRAINT DF_microlesson_updated_at_existing DEFAULT SYSUTCDATETIME() FOR updated_at;
IF NOT EXISTS (SELECT 1 FROM sys.default_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.microlesson'),N'is_deleted','ColumnId'))
    ALTER TABLE dbo.microlesson ADD CONSTRAINT DF_microlesson_is_deleted_existing DEFAULT 0 FOR is_deleted;

IF EXISTS (
    SELECT 1 FROM dbo.microlesson ml
    LEFT JOIN dbo.scenario s ON s.id=ml.scenario_id AND s.client_id=ml.client_id
    WHERE s.id IS NULL
)
    THROW 51000, 'Hay microlecciones cuyo escenario no pertenece al cliente.', 1;

IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND type='PK')
    ALTER TABLE dbo.microlesson ADD CONSTRAINT PK_microlesson_existing PRIMARY KEY(id);

IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'FK_microlesson_client')
    ALTER TABLE dbo.microlesson WITH CHECK ADD CONSTRAINT FK_microlesson_client FOREIGN KEY(client_id) REFERENCES dbo.client(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'FK_microlesson_scenario')
    ALTER TABLE dbo.microlesson WITH CHECK ADD CONSTRAINT FK_microlesson_scenario FOREIGN KEY(scenario_id) REFERENCES dbo.scenario(id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.scenario') AND name=N'UQ_scenario_id_client')
    CREATE UNIQUE INDEX UQ_scenario_id_client ON dbo.scenario(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'FK_microlesson_scenario_client')
    ALTER TABLE dbo.microlesson WITH CHECK ADD CONSTRAINT FK_microlesson_scenario_client
        FOREIGN KEY(scenario_id,client_id) REFERENCES dbo.scenario(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'CK_microlesson_status')
    ALTER TABLE dbo.microlesson WITH CHECK ADD CONSTRAINT CK_microlesson_status CHECK(status IN ('active','archived'));
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'CK_microlesson_duration')
    ALTER TABLE dbo.microlesson WITH CHECK ADD CONSTRAINT CK_microlesson_duration CHECK(duration_minutes IS NULL OR duration_minutes > 0);
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'CK_microlesson_video_size')
    ALTER TABLE dbo.microlesson WITH CHECK ADD CONSTRAINT CK_microlesson_video_size CHECK(video_size_bytes IS NULL OR video_size_bytes > 0);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'idx_microlesson_client_status')
    CREATE INDEX idx_microlesson_client_status ON dbo.microlesson(client_id,status,is_deleted);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'idx_microlesson_scenario')
    CREATE INDEX idx_microlesson_scenario ON dbo.microlesson(scenario_id,is_deleted);
"""


def _profile(cursor, claims, *, master=False, spokesperson=False):
    profile = store.resolve_user(cursor, claims, master=master)
    if spokesperson and profile["role"] != "spokesperson":
        raise HTTPException(403, "Se requiere el rol spokesperson.")
    return profile


def _base_select():
    return """SELECT ml.id,ml.client_id AS clientId,c.name AS clientName,
        ml.scenario_id AS scenarioId,s.title AS scenarioTitle,ml.title,
        ml.topic_tag AS topicTag,ml.duration_minutes AS durationMinutes,
        ml.learning_objective AS learningObjective,ml.theory_content AS theoryContent,
        ml.example_content AS exampleContent,ml.video_blob_path AS videoBlobPath,
        ml.video_file_name AS videoFileName,ml.video_content_type AS videoContentType,
        ml.video_size_bytes AS videoSizeBytes,ml.status,ml.created_at AS createdAt,
        ml.updated_at AS updatedAt
        FROM dbo.microlesson ml
        JOIN dbo.client c ON c.id=ml.client_id
        JOIN dbo.scenario s ON s.id=ml.scenario_id"""


def _serialize(items):
    for item in items:
        item["id"] = str(item["id"])
        item["clientId"] = str(item["clientId"])
        item["scenarioId"] = str(item["scenarioId"])
        item["hasVideo"] = bool(item.get("videoBlobPath"))
    return items


def list_master(connection_string, claims, client_id=None, status="all"):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        params = []
        sql = _base_select() + " WHERE ml.is_deleted=0"
        if client_id:
            sql += " AND ml.client_id=?"
            params.append(store.uid(client_id))
        if status != "all":
            sql += " AND ml.status=?"
            params.append(status)
        sql += " ORDER BY ml.updated_at DESC,ml.id"
        cursor.execute(sql, tuple(params))
        items = _serialize(store.rows(cursor))
        return {"items": items, "total": len(items)}


def get_master(connection_string, claims, microlesson_id):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        cursor.execute(_base_select() + " WHERE ml.id=? AND ml.is_deleted=0", store.uid(microlesson_id))
        items = _serialize(store.rows(cursor))
        if not items:
            raise HTTPException(404, "Microleccion no encontrada.")
        return items[0]


def clients(connection_string, claims, status="all"):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        sql = "SELECT id,name,status FROM dbo.client WHERE is_deleted=0"
        params = []
        if status != "all":
            sql += " AND status=?"
            params.append(status)
        cursor.execute(sql + " ORDER BY name,id", tuple(params))
        items = store.rows(cursor)
        for item in items:
            item["id"] = str(item["id"])
        return {"items": items}


def scenarios_for_client(connection_string, claims, client_id, status="active"):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        client_id = store.uid(client_id)
        cursor.execute("SELECT id FROM dbo.client WHERE id=? AND is_deleted=0", client_id)
        if not cursor.fetchone():
            raise HTTPException(404, "Cliente no encontrado.")
        sql = """SELECT s.id,s.title,s.status FROM dbo.scenario s
                 JOIN dbo.topic t ON t.id=s.topic_id
                 WHERE s.client_id=? AND s.is_deleted=0 AND t.is_deleted=0"""
        params = [client_id]
        if status != "all":
            sql += " AND s.status=? AND t.status='active'"
            params.append(status)
        cursor.execute(sql + " ORDER BY s.title,s.id", tuple(params))
        items = store.rows(cursor)
        for item in items:
            item["id"] = str(item["id"])
        return {"items": items}


def _validate_relation(cursor, client_id, scenario_id, require_active):
    sql = """SELECT s.id FROM dbo.scenario s
             JOIN dbo.topic t ON t.id=s.topic_id
             JOIN dbo.client c ON c.id=s.client_id
             WHERE s.id=? AND s.client_id=? AND s.is_deleted=0 AND t.is_deleted=0 AND c.is_deleted=0"""
    if require_active:
        sql += " AND s.status='active' AND t.status='active' AND c.status='active'"
    cursor.execute(sql, scenario_id, client_id)
    if not cursor.fetchone():
        detail = "El escenario no pertenece al cliente seleccionado."
        if require_active:
            detail += " Ademas, cliente, tema y escenario deben estar activos."
        raise HTTPException(422, detail)


def save(connection_string, claims, payload, microlesson_id=None):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        client_id = str(payload.clientId)
        scenario_id = str(payload.scenarioId)
        _validate_relation(cursor, client_id, scenario_id, payload.status == "active")
        if microlesson_id:
            microlesson_id = store.uid(microlesson_id)
            cursor.execute("SELECT id FROM dbo.microlesson WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND is_deleted=0", microlesson_id)
            if not cursor.fetchone():
                raise HTTPException(404, "Microleccion no encontrada.")
            cursor.execute("""UPDATE dbo.microlesson SET client_id=?,scenario_id=?,title=?,topic_tag=?,
                duration_minutes=?,learning_objective=?,theory_content=?,example_content=?,status=?,
                updated_at=SYSUTCDATETIME() WHERE id=?""",
                client_id, scenario_id, payload.title, payload.topicTag, payload.durationMinutes,
                payload.learningObjective, payload.theoryContent, payload.exampleContent,
                payload.status, microlesson_id)
        else:
            microlesson_id = str(uuid.uuid4())
            cursor.execute("""INSERT INTO dbo.microlesson(
                id,client_id,scenario_id,title,topic_tag,duration_minutes,learning_objective,
                theory_content,example_content,status,is_deleted)
                VALUES(?,?,?,?,?,?,?,?,?,?,0)""", microlesson_id, client_id, scenario_id,
                payload.title, payload.topicTag, payload.durationMinutes, payload.learningObjective,
                payload.theoryContent, payload.exampleContent, payload.status)
    return get_master(connection_string, claims, microlesson_id)


def set_status(connection_string, claims, microlesson_id, status):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        microlesson_id = store.uid(microlesson_id)
        cursor.execute("""SELECT client_id,scenario_id FROM dbo.microlesson WITH (UPDLOCK,HOLDLOCK)
                          WHERE id=? AND is_deleted=0""", microlesson_id)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Microleccion no encontrada.")
        if status == "active":
            _validate_relation(cursor, str(row[0]), str(row[1]), True)
        cursor.execute("UPDATE dbo.microlesson SET status=?,updated_at=SYSUTCDATETIME() WHERE id=?", status, microlesson_id)
    return get_master(connection_string, claims, microlesson_id)


def video_owner(connection_string, claims, microlesson_id):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        microlesson_id = store.uid(microlesson_id)
        cursor.execute("SELECT client_id,video_blob_path FROM dbo.microlesson WHERE id=? AND is_deleted=0", microlesson_id)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Microleccion no encontrada.")
        return {"id": microlesson_id, "clientId": str(row[0]), "videoBlobPath": row[1]}


def set_video(connection_string, claims, microlesson_id, blob_path, file_name, content_type, size_bytes):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        microlesson_id = store.uid(microlesson_id)
        cursor.execute("SELECT video_blob_path FROM dbo.microlesson WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND is_deleted=0", microlesson_id)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Microleccion no encontrada.")
        old_path = row[0]
        cursor.execute("""UPDATE dbo.microlesson SET video_blob_path=?,video_file_name=?,video_content_type=?,
            video_size_bytes=?,updated_at=SYSUTCDATETIME() WHERE id=?""",
            blob_path, file_name, content_type, size_bytes, microlesson_id)
    return old_path


def clear_video(connection_string, claims, microlesson_id):
    with store.database(connection_string) as cursor:
        _profile(cursor, claims, master=True)
        microlesson_id = store.uid(microlesson_id)
        cursor.execute("SELECT video_blob_path FROM dbo.microlesson WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND is_deleted=0", microlesson_id)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Microleccion no encontrada.")
        old_path = row[0]
        cursor.execute("""UPDATE dbo.microlesson SET video_blob_path=NULL,video_file_name=NULL,
            video_content_type=NULL,video_size_bytes=NULL,updated_at=SYSUTCDATETIME() WHERE id=?""", microlesson_id)
    return old_path


def list_spokesperson(connection_string, claims):
    with store.database(connection_string) as cursor:
        profile = _profile(cursor, claims, spokesperson=True)
        cursor.execute(_base_select() + """ JOIN dbo.topic t ON t.id=s.topic_id
            WHERE ml.client_id=? AND ml.status='active' AND ml.is_deleted=0
            AND s.client_id=ml.client_id AND s.status='active' AND s.is_deleted=0
            AND t.status='active' AND t.is_deleted=0 AND c.status='active' AND c.is_deleted=0
            ORDER BY ml.updated_at DESC,ml.id""", profile["client_id"])
        items = _serialize(store.rows(cursor))
        for item in items:
            item.pop("videoBlobPath", None)
        return {"items": items, "total": len(items)}


def get_spokesperson(connection_string, claims, microlesson_id):
    with store.database(connection_string) as cursor:
        profile = _profile(cursor, claims, spokesperson=True)
        cursor.execute(_base_select() + """ JOIN dbo.topic t ON t.id=s.topic_id
            WHERE ml.id=? AND ml.client_id=? AND ml.status='active' AND ml.is_deleted=0
            AND s.client_id=ml.client_id AND s.status='active' AND s.is_deleted=0
            AND t.status='active' AND t.is_deleted=0 AND c.status='active' AND c.is_deleted=0""",
            store.uid(microlesson_id), profile["client_id"])
        items = _serialize(store.rows(cursor))
        if not items:
            raise HTTPException(404, "Microleccion no disponible para tu empresa.")
        item = items[0]
        item.pop("videoBlobPath", None)
        return item


def playback_path(connection_string, claims, microlesson_id, master=False):
    if master:
        item = get_master(connection_string, claims, microlesson_id)
    else:
        item = get_spokesperson(connection_string, claims, microlesson_id)
        # La ruta nunca sale en la respuesta publica; se vuelve a consultar tras autorizar.
        with store.database(connection_string) as cursor:
            _profile(cursor, claims, spokesperson=True)
            cursor.execute("SELECT video_blob_path FROM dbo.microlesson WHERE id=?", store.uid(microlesson_id))
            row = cursor.fetchone()
            item["videoBlobPath"] = row[0] if row else None
    if not item.get("videoBlobPath"):
        raise HTTPException(404, "La microleccion no tiene video.")
    return item["videoBlobPath"]
