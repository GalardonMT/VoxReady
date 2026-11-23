"""CLI to apply the additive idempotent dbo.session_turn migration to Azure SQL."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env", override=False)
except ImportError:
    pass

from interview_live.migration import ensure_session_turn_schema


def main() -> int:
    conn_str = (
        os.getenv("SQL_CONNECTION_STRING")
        or os.getenv("AZURE_SQL_CONNECTION_STRING")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not conn_str:
        print("ERROR: SQL_CONNECTION_STRING no está configurada.", file=sys.stderr)
        return 1

    ensure_session_turn_schema(conn_str)
    print("OK: Tabla dbo.session_turn e índices verificados/creados correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
