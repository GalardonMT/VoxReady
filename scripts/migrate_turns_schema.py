#!/usr/bin/env python3
"""
Migración idempotente de base de datos para soportar:
1. Columna analysis_job_id en tabla report
2. Columna response_text en tabla session_question
"""
import os
import re
import sys
from pathlib import Path
import pyodbc
from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / "backend" / ".env", override=True)
load_dotenv(_REPO_ROOT / ".env", override=False)

SQL_CONN_STR = os.getenv("SQL_CONNECTION_STRING") or os.getenv("DATABASE_URL") or ""

def get_conn():
    if not SQL_CONN_STR:
        raise ValueError("No se encontró SQL_CONNECTION_STRING")
    installed_drivers = pyodbc.drivers()
    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    chosen = None
    for d in preferred:
        if d in installed_drivers:
            chosen = d
            break
    if not chosen:
        raise RuntimeError(f"No se encontró un driver ODBC compatible: {installed_drivers}")

    conn_str = SQL_CONN_STR
    if "Driver={" in conn_str:
        conn_str = re.sub(r"Driver=\{[^}]+\}", f"Driver={{{chosen}}}", conn_str, flags=re.IGNORECASE)
    elif "DRIVER=" not in conn_str.upper():
        conn_str = f"DRIVER={{{chosen}}};{conn_str}"

    if chosen != "SQL Server" and "Encrypt=" not in conn_str and "ENCRYPT=" not in conn_str:
        conn_str += ";Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"

    return pyodbc.connect(conn_str, timeout=30)

def run_migration():
    print("=" * 80)
    print(" FASE 1: MIGRACIÓN IDEMPOTENTE EN AZURE SQL (sqldb-voxready)")
    print("=" * 80)

    conn = get_conn()
    cur = conn.cursor()

    try:
        # 1. Columna analysis_job_id en report
        print("[*] Verificando columna 'analysis_job_id' en tabla 'report'...")
        cur.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'report' AND COLUMN_NAME = 'analysis_job_id'
            )
            BEGIN
                ALTER TABLE report ADD analysis_job_id UNIQUEIDENTIFIER NULL;
                PRINT 'Columna analysis_job_id añadida a report.';
            END
        """)
        conn.commit()
        print(" [+] Columna 'analysis_job_id' verificada/creada en 'report'.")

        # 2. Columna response_text en session_question
        print("[*] Verificando columna 'response_text' en tabla 'session_question'...")
        cur.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'session_question' AND COLUMN_NAME = 'response_text'
            )
            BEGIN
                ALTER TABLE session_question ADD response_text NVARCHAR(MAX) NULL;
                PRINT 'Columna response_text añadida a session_question.';
            END
        """)
        conn.commit()
        print(" [+] Columna 'response_text' verificada/creada en 'session_question'.")

        # 3. Verificar estructura final
        cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'report'")
        rep_cols = [f"{r[0]} ({r[1]})" for r in cur.fetchall()]
        print(f"\n[+] Columnas en 'report': {', '.join(rep_cols)}")

        cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'session_question'")
        sq_cols = [f"{r[0]} ({r[1]})" for r in cur.fetchall()]
        print(f"[+] Columnas en 'session_question': {', '.join(sq_cols)}")

        print("\n[+] Migración de Fase 1 completada exitosamente.")

    except Exception as e:
        conn.rollback()
        print(f"\n[-] ERROR en migración: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_migration()
