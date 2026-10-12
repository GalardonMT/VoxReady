#!/usr/bin/env python3
"""Migración aditiva de Fase 2; conserva todas las filas y relaciones."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master_topics import MASTER_SCHEMA_DDL
from seed_master_topics import connect


def main():
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute('SET XACT_ABORT ON')
        cursor.execute(MASTER_SCHEMA_DDL)
        cursor.execute("""UPDATE q SET sort_order=assigned.position
            FROM dbo.question q JOIN (SELECT question_id,MIN(sequence_no) AS position
            FROM dbo.scenario_question WHERE status='active' GROUP BY question_id) assigned
            ON assigned.question_id=q.id WHERE q.sort_order=0""")
        for table, column in [('question', 'sort_order'), ('topic_key_message', 'status'), ('topic_red_line', 'status'), ('scenario_question', 'status')]:
            cursor.execute('SELECT COL_LENGTH(?,?)', 'dbo.' + table, column)
            if cursor.fetchone()[0] is None:
                raise RuntimeError('Migración incompleta: ' + table + '.' + column)
        connection.commit()
        print('Fase 2: columnas aditivas verificadas en Azure SQL.')
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == '__main__':
    main()
