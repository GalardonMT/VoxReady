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
from microlessons import MICROLESSON_SCHEMA_DDL, MICROLESSON_DATA_DDL, MICROLESSON_CONSTRAINT_DDL
from seed_master_topics import connect, SeedError, SCENARIO_QUESTION_DDL, verify_link_schema

REQUIRED = {
    'topic': ('client_id',), 'question': ('client_id', 'sort_order'),
    'topic_key_message': ('status',), 'topic_red_line': ('status',),
    'scenario_question': ('status', 'sequence_no'),
    'session': ('external_session_id', 'idempotency_key'),
    'session_question': ('question_text',),
    'microlesson': ('client_id', 'scenario_id', 'learning_objective', 'theory_content',
                    'video_blob_path', 'status', 'is_deleted', 'deleted_at'),
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
    cursor.execute("""SELECT is_nullable FROM sys.columns
                      WHERE object_id=OBJECT_ID('dbo.microlesson') AND name='scenario_id'""")
    scenario_column = cursor.fetchone()
    if not scenario_column or scenario_column[0]:
        raise SeedError('dbo.microlesson.scenario_id debe ser obligatorio.')
    required_not_null = (
        'id', 'client_id', 'scenario_id', 'title', 'learning_objective',
        'theory_content', 'status', 'created_at', 'updated_at', 'is_deleted',
    )
    for column in required_not_null:
        cursor.execute("""SELECT is_nullable FROM sys.columns
                          WHERE object_id=OBJECT_ID('dbo.microlesson') AND name=?""", column)
        row = cursor.fetchone()
        if not row or row[0]:
            raise SeedError(f'dbo.microlesson.{column} debe ser obligatorio.')
    cursor.execute("""SELECT is_nullable FROM sys.columns
                      WHERE object_id=OBJECT_ID('dbo.microlesson') AND name='video_blob_path'""")
    video_path = cursor.fetchone()
    if not video_path or not video_path[0]:
        raise SeedError('dbo.microlesson.video_blob_path debe seguir siendo opcional.')
    cursor.execute("""SELECT c.name FROM sys.key_constraints kc
        JOIN sys.index_columns ic ON ic.object_id=kc.parent_object_id AND ic.index_id=kc.unique_index_id
        JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
        WHERE kc.parent_object_id=OBJECT_ID('dbo.microlesson') AND kc.type='PK'""")
    primary_columns = [row[0] for row in cursor.fetchall()]
    if primary_columns != ['id']:
        raise SeedError('dbo.microlesson debe usar id como clave primaria unica.')
    for constraint in ('FK_microlesson_client', 'FK_microlesson_scenario',
                       'FK_microlesson_scenario_client', 'CK_microlesson_status'):
        cursor.execute("""SELECT is_disabled,is_not_trusted FROM sys.foreign_keys
                          WHERE parent_object_id=OBJECT_ID('dbo.microlesson') AND name=?
                          UNION ALL
                          SELECT is_disabled,is_not_trusted FROM sys.check_constraints
                          WHERE parent_object_id=OBJECT_ID('dbo.microlesson') AND name=?""", constraint, constraint)
        row = cursor.fetchone()
        if not row or row[0] or row[1]:
            raise SeedError(f'Falta la restriccion activa y confiable {constraint}.')
    for constraint in ('CK_microlesson_duration', 'CK_microlesson_video_size'):
        cursor.execute("""SELECT is_disabled,is_not_trusted FROM sys.check_constraints
                          WHERE parent_object_id=OBJECT_ID('dbo.microlesson') AND name=?""", constraint)
        row = cursor.fetchone()
        if not row or row[0] or row[1]:
            raise SeedError(f'Falta la restriccion activa y confiable {constraint}.')
    for table, index, unique in (
        ('microlesson', 'idx_microlesson_client_status', False),
        ('microlesson', 'idx_microlesson_scenario', False),
        ('scenario', 'UQ_scenario_id_client', True),
    ):
        cursor.execute("""SELECT is_unique,is_disabled FROM sys.indexes
                          WHERE object_id=OBJECT_ID(?) AND name=?""", 'dbo.' + table, index)
        row = cursor.fetchone()
        if not row or bool(row[0]) != unique or row[1]:
            raise SeedError(f'Falta el indice activo {index}.')
    for index in ('UQ_session_external_id', 'UQ_session_idempotency'):
        cursor.execute("SELECT is_unique,is_disabled FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.session') AND name=?", index)
        row = cursor.fetchone()
        if not row or not row[0] or row[1]:
            raise SeedError(f'Falta el índice activo {index}.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--connection-only', action='store_true', help='Comprueba motor y base sin inspeccionar ni modificar el esquema.')
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
        if args.connection_only:
            connection.rollback()
            print(f'Azure SQL {name}: conexión verificada en modo solo lectura; no se inspeccionó ni modificó el esquema.')
            return 0
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
            cursor.execute(MICROLESSON_SCHEMA_DDL)
            cursor.execute(MICROLESSON_DATA_DDL)
            cursor.execute(MICROLESSON_CONSTRAINT_DDL)
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
