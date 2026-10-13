"""Persistencia de empresas cliente para la configuracion maestra."""
import uuid


CLIENT_SCHEMA_DDL = """
IF OBJECT_ID(N'dbo.client', N'U') IS NULL
    THROW 51000, 'Falta la tabla existente dbo.client; no se creo una tabla sustituta.', 1;

IF COL_LENGTH('dbo.client', 'created_at') IS NULL
    ALTER TABLE dbo.client ADD created_at DATETIME2 NOT NULL
        CONSTRAINT DF_client_created_at DEFAULT SYSUTCDATETIME();
IF COL_LENGTH('dbo.client', 'updated_at') IS NULL
    ALTER TABLE dbo.client ADD updated_at DATETIME2 NOT NULL
        CONSTRAINT DF_client_updated_at DEFAULT SYSUTCDATETIME();
IF COL_LENGTH('dbo.client', 'is_deleted') IS NULL
    ALTER TABLE dbo.client ADD is_deleted BIT NOT NULL
        CONSTRAINT DF_client_is_deleted DEFAULT 0;
IF COL_LENGTH('dbo.client', 'deleted_at') IS NULL
    ALTER TABLE dbo.client ADD deleted_at DATETIME2 NULL;

IF COL_LENGTH('dbo.client', 'id') IS NULL
    THROW 51000, 'dbo.client no contiene la clave id esperada.', 1;
IF COL_LENGTH('dbo.client', 'name') IS NULL
    THROW 51000, 'dbo.client no contiene el nombre esperado.', 1;
IF COL_LENGTH('dbo.client', 'status') IS NULL
    THROW 51000, 'dbo.client no contiene el estado esperado.', 1;
IF EXISTS (
    SELECT 1 FROM dbo.client
    WHERE name IS NULL OR LEN(LTRIM(RTRIM(CONVERT(NVARCHAR(MAX), name)))) NOT BETWEEN 1 AND 150
)
    THROW 51000, 'Hay clientes con nombres vacios o de mas de 150 caracteres; no se modificaron.', 1;
IF EXISTS (
    SELECT 1 FROM dbo.client
    WHERE status IS NULL OR status NOT IN ('active', 'suspended')
)
    THROW 51000, 'Hay clientes con estados incompatibles; no se modificaron.', 1;

ALTER TABLE dbo.client ALTER COLUMN name NVARCHAR(150) NOT NULL;
ALTER TABLE dbo.client ALTER COLUMN status NVARCHAR(20) NOT NULL;

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id=OBJECT_ID(N'dbo.client')
      AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.client'),N'created_at','ColumnId')
)
    ALTER TABLE dbo.client ADD CONSTRAINT DF_client_created_at_existing
        DEFAULT SYSUTCDATETIME() FOR created_at;
IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id=OBJECT_ID(N'dbo.client')
      AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.client'),N'updated_at','ColumnId')
)
    ALTER TABLE dbo.client ADD CONSTRAINT DF_client_updated_at_existing
        DEFAULT SYSUTCDATETIME() FOR updated_at;
IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id=OBJECT_ID(N'dbo.client')
      AND parent_column_id=COLUMNPROPERTY(OBJECT_ID(N'dbo.client'),N'is_deleted','ColumnId')
)
    ALTER TABLE dbo.client ADD CONSTRAINT DF_client_is_deleted_existing
        DEFAULT 0 FOR is_deleted;

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id=OBJECT_ID(N'dbo.client') AND name=N'CK_client_status'
)
    ALTER TABLE dbo.client WITH CHECK ADD CONSTRAINT CK_client_status
        CHECK (status IN ('active', 'suspended'));
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id=OBJECT_ID(N'dbo.client') AND name=N'CK_client_name'
)
    ALTER TABLE dbo.client WITH CHECK ADD CONSTRAINT CK_client_name
        CHECK (LEN(LTRIM(RTRIM(name))) BETWEEN 1 AND 150);
"""


def _serialize(row, columns):
    item = dict(zip(columns, row))
    item["id"] = str(item["id"])
    item["isDeleted"] = bool(item["isDeleted"])
    return item


def list_clients(cursor, status="all"):
    sql = """SELECT id,name,status,created_at AS createdAt,updated_at AS updatedAt,
                    is_deleted AS isDeleted,deleted_at AS deletedAt
             FROM dbo.client WHERE is_deleted=0"""
    parameters = ()
    if status != "all":
        sql += " AND status=?"
        parameters = (status,)
    sql += " ORDER BY name,id"
    cursor.execute(sql, *parameters)
    columns = [column[0] for column in cursor.description]
    return [_serialize(row, columns) for row in cursor.fetchall()]


def create_client(cursor, name, status):
    client_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO dbo.client(id,name,status) VALUES(?,?,?)",
        client_id,
        name,
        status,
    )
    cursor.execute(
        """SELECT id,name,status,created_at AS createdAt,updated_at AS updatedAt,
                  is_deleted AS isDeleted,deleted_at AS deletedAt
           FROM dbo.client WHERE id=? AND is_deleted=0""",
        client_id,
    )
    columns = [column[0] for column in cursor.description]
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("El cliente creado no pudo recuperarse.")
    return _serialize(row, columns)
