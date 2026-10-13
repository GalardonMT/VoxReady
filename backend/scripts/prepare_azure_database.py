#!/usr/bin/env python3
"""Preparación Docker de Azure SQL: migraciones aditivas, sin seed automático.

--verify-only comprueba conexión y esquema sin escrituras.
Los ejemplos se cargan explícitamente con seed_master_topics.py.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master_topics import MASTER_SCHEMA_DDL
from spokesperson_store import SESSION_SCHEMA_DDL, SESSION_INDEX_DDL
from progress_migration import (
    PROGRESS_SCHEMA_DDL,
    PROGRESS_SCHEMA_STEPS,
    USER_AREA_PROGRESS_BACKFILL_DML,
)
from seed_master_topics import connect, SeedError, SCENARIO_QUESTION_DDL, verify_link_schema

REQUIRED = {
    'topic': ('client_id',), 'question': ('client_id', 'sort_order'),
    'topic_key_message': ('status',), 'topic_red_line': ('status',),
    'scenario_question': ('status', 'sequence_no'),
    'session': ('external_session_id', 'idempotency_key'),
    'session_question': ('question_text',),
    'schedule': ('session_id',),
    'user_area_progress': (
        'user_id', 'rubric_area_id', 'current_value', 'delta',
        'sessions_count', 'last_session_at',
    ),
}

REQUIRED_INDEXES = {
    'session': {
        'UQ_session_external_id': {'unique': True, 'filtered': True},
        'UQ_session_idempotency': {'unique': True, 'filtered': True},
    },
    'schedule': {
        'UQ_schedule_session': {
            'unique': True, 'filtered': True, 'keys': ('session_id',),
            'includes': (), 'filter': 'session_idisnotnull',
        },
        'IX_schedule_client_user_date': {
            'unique': False, 'filtered': False,
            'keys': ('client_id', 'user_id', 'scheduled_date', 'status'),
            'includes': ('scenario_id', 'session_id', 'updated_at'),
        },
    },
    'user_area_progress': {
        'UQ_user_area_progress_user_area': {
            'unique': True, 'filtered': False,
            'keys': ('user_id', 'rubric_area_id'), 'includes': (),
        },
    },
}


def verify(cursor):
    for table, columns in REQUIRED.items():
        for column in columns:
            cursor.execute('SELECT COL_LENGTH(?,?)', 'dbo.' + table, column)
            if cursor.fetchone()[0] is None:
                raise SeedError(f'Falta dbo.{table}.{column}; ejecuta la preparación de Azure SQL.')
    for table in ('topic', 'question'):
        cursor.execute("SELECT is_nullable FROM sys.columns WHERE object_id=OBJECT_ID(?) AND name='client_id'", 'dbo.' + table)
        row = cursor.fetchone()
        if not row or not row[0]:
            raise SeedError(f'dbo.{table}.client_id no admite los temas maestros globales.')
    verify_link_schema(cursor)
    cursor.execute("""SELECT is_nullable, TYPE_NAME(user_type_id)
                      FROM sys.columns
                      WHERE object_id=OBJECT_ID(N'dbo.schedule') AND name=N'session_id'""")
    session_column = cursor.fetchone()
    if not session_column or not session_column[0] or session_column[1].lower() != 'uniqueidentifier':
        raise SeedError('dbo.schedule.session_id debe ser UNIQUEIDENTIFIER NULL.')
    for table, indexes in REQUIRED_INDEXES.items():
        for index, expected in indexes.items():
            cursor.execute("""SELECT is_unique,is_disabled,has_filter,filter_definition
                              FROM sys.indexes
                              WHERE object_id=OBJECT_ID(?) AND name=?""",
                           'dbo.' + table, index)
            row = cursor.fetchone()
            if (not row or bool(row[0]) != expected['unique'] or row[1]
                    or bool(row[2]) != expected['filtered']):
                raise SeedError(f'Falta o no coincide el índice activo {index}.')
            if 'keys' in expected:
                cursor.execute("""SELECT c.name,ic.key_ordinal,ic.is_included_column,ic.index_column_id
                                  FROM sys.indexes i
                                  JOIN sys.index_columns ic
                                    ON ic.object_id=i.object_id AND ic.index_id=i.index_id
                                  JOIN sys.columns c
                                    ON c.object_id=ic.object_id AND c.column_id=ic.column_id
                                  WHERE i.object_id=OBJECT_ID(?) AND i.name=?
                                  ORDER BY ic.index_column_id""",
                               'dbo.' + table, index)
                columns = list(cursor.fetchall())
                keys = tuple(
                    column[0].lower()
                    for column in sorted(
                        (column for column in columns if not column[2]),
                        key=lambda column: column[1],
                    )
                )
                includes = tuple(column[0].lower() for column in columns if column[2])
                if keys != expected['keys'] or includes != expected['includes']:
                    raise SeedError(f'Las columnas del índice {index} no coinciden.')
                expected_filter = expected.get('filter')
                actual_filter = ''.join(
                    str(row[3] or '').lower().replace('[', '').replace(']', '').split()
                ).replace('(', '').replace(')', '')
                if expected_filter and actual_filter != expected_filter:
                    raise SeedError(f'El filtro del índice {index} no coincide.')
    cursor.execute("""SELECT fk.is_disabled,fk.is_not_trusted,parent_col.name,referenced_col.name
                      FROM sys.foreign_keys AS fk
                      JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id=fk.object_id
                      JOIN sys.columns AS parent_col
                        ON parent_col.object_id=fkc.parent_object_id
                       AND parent_col.column_id=fkc.parent_column_id
                      JOIN sys.columns AS referenced_col
                        ON referenced_col.object_id=fkc.referenced_object_id
                       AND referenced_col.column_id=fkc.referenced_column_id
                      WHERE fk.parent_object_id=OBJECT_ID(N'dbo.schedule')
                        AND fk.referenced_object_id=OBJECT_ID(N'dbo.session')
                        AND fk.name=N'FK_schedule_session'""")
    foreign_key = cursor.fetchone()
    if (not foreign_key or foreign_key[0] or foreign_key[1]
            or foreign_key[2].lower() != 'session_id'
            or foreign_key[3].lower() != 'id'):
        raise SeedError('Falta la clave foránea activa y verificada FK_schedule_session.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(argv)
    connection = None
    try:
        connection = connect()
        connection.timeout = 60
        cursor = connection.cursor()
        cursor.execute("SELECT CONVERT(int,SERVERPROPERTY('EngineEdition')),DB_NAME()")
        engine, name = cursor.fetchone()
        if engine not in (5, 8):
            raise SeedError('El despliegue requiere Azure SQL Database o Azure SQL Managed Instance. No se migró la base configurada.')
        if not args.verify_only:
            cursor.execute('SET XACT_ABORT ON; SET LOCK_TIMEOUT 30000; IF @@TRANCOUNT=0 BEGIN TRANSACTION;')
            cursor.execute("""DECLARE @r int;
                EXEC @r=sys.sp_getapplock @Resource='voxready-azure-schema-v1',
                     @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=30000;
                IF @r<0 THROW 51000,'No se pudo bloquear la migración',1;""")
            for table in ('topic', 'question'):
                cursor.execute("SELECT is_nullable FROM sys.columns WHERE object_id=OBJECT_ID(?) AND name='client_id'", 'dbo.' + table)
                column = cursor.fetchone()
                if not column:
                    raise SeedError(f'Falta dbo.{table}.client_id en la base existente.')
                if not column[0]:
                    cursor.execute(f'ALTER TABLE dbo.[{table}] ALTER COLUMN client_id UNIQUEIDENTIFIER NULL')
            cursor.execute(SCENARIO_QUESTION_DDL)
            # Batches separados para compilar después de añadir cada columna.
            cursor.execute(MASTER_SCHEMA_DDL)
            cursor.execute("""UPDATE q SET sort_order=assigned.position FROM dbo.question q
                JOIN (SELECT question_id,MIN(sequence_no) AS position FROM dbo.scenario_question
                      WHERE status='active' GROUP BY question_id) assigned
                ON assigned.question_id=q.id WHERE q.sort_order=0""")
            cursor.execute(SESSION_SCHEMA_DDL)
            cursor.execute(SESSION_INDEX_DDL)
            for ddl in PROGRESS_SCHEMA_STEPS:
                cursor.execute(ddl)
            cursor.execute(USER_AREA_PROGRESS_BACKFILL_DML)
        verify(cursor)
        if args.verify_only:
            connection.rollback()
        else:
            connection.commit()
        print(f'Azure SQL {name}: conexión y esquema verificados. Preparación sin borrados ni seed automático.')
        return 0
    except SeedError as error:
        if connection:
            connection.rollback()
        print(f'ERROR: {error}', file=sys.stderr)
    except Exception as error:
        if connection:
            connection.rollback()
        print(f'ERROR: preparación fallida ({type(error).__name__}); transacción revertida. Revisa conexión, esquema y permisos.', file=sys.stderr)
    finally:
        if connection:
            connection.close()
    return 1


if __name__ == '__main__':
    sys.exit(main())
