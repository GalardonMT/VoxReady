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
from seed_master_topics import connect, SeedError, SCENARIO_QUESTION_DDL, verify_link_schema

REQUIRED = {
    'topic': ('client_id',), 'question': ('client_id', 'sort_order'),
    'topic_key_message': ('status',), 'topic_red_line': ('status',),
    'scenario_question': ('status', 'sequence_no'),
    'session': ('external_session_id', 'idempotency_key'),
    'session_question': ('question_text',),
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
    for index in ('UQ_session_external_id', 'UQ_session_idempotency'):
        cursor.execute("SELECT is_unique,is_disabled FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.session') AND name=?", index)
        row = cursor.fetchone()
        if not row or not row[0] or row[1]:
            raise SeedError(f'Falta el índice activo {index}.')


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
