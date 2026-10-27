"""Additive Azure SQL schema for manually assigned micro-lessons.

No content or assignments are seeded. Existing completed and revoked cycles remain
historical rows; only pending states participate in the filtered unique index.
"""

ASSIGNMENT_SCHEMA_STEPS = (
    """
IF OBJECT_ID(N'dbo.microlesson_assignment', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.microlesson_assignment (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_microlesson_assignment PRIMARY KEY,
        client_id UNIQUEIDENTIFIER NOT NULL,
        microlesson_id UNIQUEIDENTIFIER NOT NULL,
        user_id UNIQUEIDENTIFIER NOT NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_microlesson_assignment_status DEFAULT 'assigned',
        sort_order INT NOT NULL,
        assigned_by UNIQUEIDENTIFIER NOT NULL,
        assigned_at DATETIME2(3) NOT NULL CONSTRAINT DF_microlesson_assignment_assigned_at DEFAULT SYSUTCDATETIME(),
        started_at DATETIME2(3) NULL,
        completed_at DATETIME2(3) NULL,
        revoked_at DATETIME2(3) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_microlesson_assignment_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_microlesson_assignment_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_microlesson_assignment_status
            CHECK (status IN ('assigned','in_progress','completed','revoked')),
        CONSTRAINT CK_microlesson_assignment_sort_order CHECK (sort_order > 0)
    );
END;
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.microlesson') AND name=N'UQ_microlesson_id_client')
    CREATE UNIQUE INDEX UQ_microlesson_id_client ON dbo.microlesson(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.app_user') AND name=N'UQ_app_user_id_client')
    CREATE UNIQUE INDEX UQ_app_user_id_client ON dbo.app_user(id,client_id);
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'FK_microlesson_assignment_client')
    ALTER TABLE dbo.microlesson_assignment WITH CHECK ADD CONSTRAINT FK_microlesson_assignment_client
        FOREIGN KEY (client_id) REFERENCES dbo.client(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'FK_microlesson_assignment_lesson_client')
    ALTER TABLE dbo.microlesson_assignment WITH CHECK ADD CONSTRAINT FK_microlesson_assignment_lesson_client
        FOREIGN KEY (microlesson_id,client_id) REFERENCES dbo.microlesson(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'FK_microlesson_assignment_user_client')
    ALTER TABLE dbo.microlesson_assignment WITH CHECK ADD CONSTRAINT FK_microlesson_assignment_user_client
        FOREIGN KEY (user_id,client_id) REFERENCES dbo.app_user(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'FK_microlesson_assignment_assigned_by')
    ALTER TABLE dbo.microlesson_assignment WITH CHECK ADD CONSTRAINT FK_microlesson_assignment_assigned_by
        FOREIGN KEY (assigned_by) REFERENCES dbo.app_user(id);
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'UQ_microlesson_assignment_active')
    CREATE UNIQUE INDEX UQ_microlesson_assignment_active
        ON dbo.microlesson_assignment(client_id,user_id,microlesson_id)
        WHERE status IN ('assigned','in_progress');
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'IX_microlesson_assignment_user')
    CREATE INDEX IX_microlesson_assignment_user
        ON dbo.microlesson_assignment(client_id,user_id,status,sort_order,assigned_at)
        INCLUDE (microlesson_id,completed_at);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=N'IX_microlesson_assignment_lesson')
    CREATE INDEX IX_microlesson_assignment_lesson
        ON dbo.microlesson_assignment(client_id,microlesson_id,status);
""",
)


ASSIGNMENT_REQUIRED_COLUMNS = (
    'id', 'client_id', 'microlesson_id', 'user_id', 'status', 'sort_order',
    'assigned_by', 'assigned_at', 'started_at', 'completed_at', 'revoked_at',
    'created_at', 'updated_at',
)


def _require_constraint(cursor, table, name, kind, error_type):
    catalog = 'sys.foreign_keys' if kind == 'foreign' else 'sys.check_constraints'
    cursor.execute(
        f"SELECT is_disabled,is_not_trusted FROM {catalog} "
        "WHERE parent_object_id=OBJECT_ID(?) AND name=?",
        'dbo.' + table, name,
    )
    row = cursor.fetchone()
    if not row or row[0] or row[1]:
        raise error_type(f'Falta o no es confiable la restricción {name}.')


def _require_index(cursor, table, name, *, unique, filtered, error_type):
    cursor.execute(
        "SELECT is_unique,is_disabled,has_filter,filter_definition FROM sys.indexes "
        "WHERE object_id=OBJECT_ID(?) AND name=?",
        'dbo.' + table, name,
    )
    row = cursor.fetchone()
    if (not row or bool(row[0]) != unique or row[1] or bool(row[2]) != filtered):
        raise error_type(f'Falta o no coincide el índice {name}.')
    if filtered:
        expression = ''.join(str(row[3] or '').lower().replace('[', '').replace(']', '').split())
        expression = expression.replace('(', '').replace(')', '')
        expression = expression.replace("=n'", "='").replace("inn'", "in'")
        allowed = {
            "statusin'assigned','in_progress'",
            "statusin'in_progress','assigned'",
            "status='assigned'orstatus='in_progress'",
            "status='in_progress'orstatus='assigned'",
        }
        if expression not in allowed:
            raise error_type(f'El filtro del índice {name} no coincide.')


def _require_index_keys(cursor, table, name, expected, error_type):
    cursor.execute(
        """SELECT c.name FROM sys.indexes i
           JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
           JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
           WHERE i.object_id=OBJECT_ID(?) AND i.name=? AND ic.key_ordinal>0
           ORDER BY ic.key_ordinal""",
        'dbo.' + table, name,
    )
    actual = tuple(row[0].lower() for row in cursor.fetchall())
    if actual != expected:
        raise error_type(f'Las columnas del índice {name} no coinciden.')


def _require_foreign_key(cursor, name, target, pairs, error_type):
    cursor.execute(
        """SELECT OBJECT_NAME(fk.referenced_object_id),pc.name,rc.name
           FROM sys.foreign_keys fk
           JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
           JOIN sys.columns pc ON pc.object_id=fkc.parent_object_id AND pc.column_id=fkc.parent_column_id
           JOIN sys.columns rc ON rc.object_id=fkc.referenced_object_id AND rc.column_id=fkc.referenced_column_id
           WHERE fk.parent_object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND fk.name=?
           ORDER BY fkc.constraint_column_id""",
        name,
    )
    actual = tuple((str(row[0]).lower(), str(row[1]).lower(), str(row[2]).lower()) for row in cursor.fetchall())
    expected = tuple((target, parent, referenced) for parent, referenced in pairs)
    if actual != expected:
        raise error_type(f'Las columnas de {name} no coinciden.')


def verify_assignment_schema(cursor, error_type):
    """Fail closed if the assignment schema loses a security boundary."""
    table = 'microlesson_assignment'
    for column in ASSIGNMENT_REQUIRED_COLUMNS:
        cursor.execute('SELECT COL_LENGTH(?,?)', 'dbo.' + table, column)
        if cursor.fetchone()[0] is None:
            raise error_type(f'Falta dbo.{table}.{column}.')

    column_specs = {
        'id': ('uniqueidentifier', False),
        'client_id': ('uniqueidentifier', False),
        'microlesson_id': ('uniqueidentifier', False),
        'user_id': ('uniqueidentifier', False),
        'assigned_by': ('uniqueidentifier', False),
        'status': ('nvarchar', False),
        'sort_order': ('int', False),
        'assigned_at': ('datetime2', False),
        'started_at': ('datetime2', True),
        'completed_at': ('datetime2', True),
        'revoked_at': ('datetime2', True),
        'created_at': ('datetime2', False),
        'updated_at': ('datetime2', False),
    }
    for column, (sql_type, nullable) in column_specs.items():
        cursor.execute(
            "SELECT TYPE_NAME(user_type_id),is_nullable FROM sys.columns "
            "WHERE object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND name=?",
            column,
        )
        row = cursor.fetchone()
        if not row or str(row[0]).lower() != sql_type or bool(row[1]) != nullable:
            raise error_type(f'dbo.microlesson_assignment.{column} tiene tipo o nulabilidad incorrecta.')

    cursor.execute(
        """SELECT c.name FROM sys.key_constraints kc
           JOIN sys.index_columns ic ON ic.object_id=kc.parent_object_id AND ic.index_id=kc.unique_index_id
           JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
           WHERE kc.parent_object_id=OBJECT_ID(N'dbo.microlesson_assignment') AND kc.type='PK'
           ORDER BY ic.key_ordinal"""
    )
    if tuple(str(row[0]).lower() for row in cursor.fetchall()) != ('id',):
        raise error_type('dbo.microlesson_assignment debe tener id como clave primaria.')

    for table_name, index_name in (
        ('microlesson', 'UQ_microlesson_id_client'),
        ('app_user', 'UQ_app_user_id_client'),
    ):
        _require_index(cursor, table_name, index_name, unique=True, filtered=False, error_type=error_type)
        _require_index_keys(cursor, table_name, index_name, ('id', 'client_id'), error_type)
    _require_index(cursor, table, 'UQ_microlesson_assignment_active', unique=True, filtered=True, error_type=error_type)
    _require_index_keys(cursor, table, 'UQ_microlesson_assignment_active', ('client_id', 'user_id', 'microlesson_id'), error_type)
    _require_index(cursor, table, 'IX_microlesson_assignment_user', unique=False, filtered=False, error_type=error_type)
    _require_index(cursor, table, 'IX_microlesson_assignment_lesson', unique=False, filtered=False, error_type=error_type)

    foreign_keys = {
        'FK_microlesson_assignment_client': ('client', (('client_id', 'id'),)),
        'FK_microlesson_assignment_lesson_client': (
            'microlesson', (('microlesson_id', 'id'), ('client_id', 'client_id')),
        ),
        'FK_microlesson_assignment_user_client': (
            'app_user', (('user_id', 'id'), ('client_id', 'client_id')),
        ),
        'FK_microlesson_assignment_assigned_by': ('app_user', (('assigned_by', 'id'),)),
    }
    for name, (target, pairs) in foreign_keys.items():
        _require_constraint(cursor, table, name, 'foreign', error_type)
        _require_foreign_key(cursor, name, target, pairs, error_type)
    for name in ('CK_microlesson_assignment_status', 'CK_microlesson_assignment_sort_order'):
        _require_constraint(cursor, table, name, 'check', error_type)
