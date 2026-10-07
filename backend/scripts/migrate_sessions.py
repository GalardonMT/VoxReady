#!/usr/bin/env python3
"""Fase 3: columnas e índices aditivos; conserva PK UUID y todas sus FK."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spokesperson_store import SESSION_SCHEMA_DDL, SESSION_INDEX_DDL
from seed_master_topics import connect


def main():
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute('SET XACT_ABORT ON')
        # Batches separados: SQL Server compila los índices después de añadir columnas.
        cursor.execute(SESSION_SCHEMA_DDL)
        cursor.execute(SESSION_INDEX_DDL)
        connection.commit()
        print('Fase 3: persistencia de sesiones y secuencia verificada en Azure SQL.')
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == '__main__':
    main()
