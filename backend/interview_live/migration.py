"""Idempotent additive Azure SQL migration for dbo.session_turn."""

from __future__ import annotations

import logging
import re

import pyodbc

logger = logging.getLogger("interview_live.migration")

SESSION_TURN_DDL = """
IF OBJECT_ID('dbo.session_turn', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.session_turn (
        id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
        session_id UNIQUEIDENTIFIER NOT NULL
            CONSTRAINT FK_session_turn_session REFERENCES dbo.session(id),
        session_question_id UNIQUEIDENTIFIER NULL
            CONSTRAINT FK_session_turn_session_question REFERENCES dbo.session_question(id),
        parent_turn_id UNIQUEIDENTIFIER NULL
            CONSTRAINT FK_session_turn_parent REFERENCES dbo.session_turn(id),
        base_sequence_no INT NOT NULL,
        turn_index INT NOT NULL,
        followup_depth INT NOT NULL DEFAULT 0,
        turn_kind NVARCHAR(20) NOT NULL
            CONSTRAINT CK_session_turn_kind CHECK (turn_kind IN ('base', 'follow_up')),
        question_text NVARCHAR(MAX) NOT NULL,
        followup_generated BIT NOT NULL DEFAULT 0,
        followup_question_text NVARCHAR(MAX) NULL,
        followup_trigger_reason NVARCHAR(500) NULL,
        start_offset_ms INT NULL,
        end_offset_ms INT NULL,
        audio_mime_type NVARCHAR(100) NULL,
        audio_bytes INT NULL,
        audio_duration_sec FLOAT NULL,
        speech_time_sec FLOAT NULL,
        silence_time_sec FLOAT NULL,
        phonation_ratio FLOAT NULL,
        acoustic_pauses_json NVARCHAR(MAX) NULL,
        transcript NVARCHAR(MAX) NULL,
        words_json NVARCHAR(MAX) NULL,
        asr_status NVARCHAR(20) NOT NULL DEFAULT 'pending'
            CONSTRAINT CK_session_turn_asr_status CHECK (
                asr_status IN ('pending', 'processing', 'completed', 'failed', 'fallback_worker')
            ),
        asr_error NVARCHAR(500) NULL,
        gemini_latency_ms INT NULL,
        ffmpeg_latency_ms INT NULL,
        parakeet_latency_ms INT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UX_session_turn_session_index'
      AND object_id = OBJECT_ID('dbo.session_turn')
)
BEGIN
    CREATE UNIQUE INDEX UX_session_turn_session_index
        ON dbo.session_turn (session_id, turn_index);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_session_turn_session_status'
      AND object_id = OBJECT_ID('dbo.session_turn')
)
BEGIN
    CREATE INDEX IX_session_turn_session_status
        ON dbo.session_turn (session_id, asr_status);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_session_turn_session_base_seq'
      AND object_id = OBJECT_ID('dbo.session_turn')
)
BEGIN
    CREATE INDEX IX_session_turn_session_base_seq
        ON dbo.session_turn (session_id, base_sequence_no, followup_depth);
END;
"""


def normalize_sql_conn_str(conn_str: str) -> str:
    """Normalize ODBC driver for Linux Docker (Driver 18) and Windows dev."""
    installed = pyodbc.drivers()
    preferred = (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    )
    chosen = next((drv for drv in preferred if drv in installed), None)
    normalized = conn_str
    if chosen and re.search(r"driver=\{[^}]+\}", normalized, flags=re.IGNORECASE):
        normalized = re.sub(
            r"driver=\{[^}]+\}",
            f"Driver={{{chosen}}}",
            normalized,
            flags=re.IGNORECASE,
        )
        if chosen == "SQL Server":
            normalized = re.sub(r";Encrypt=[^;]+", "", normalized, flags=re.IGNORECASE)
            normalized = re.sub(
                r";TrustServerCertificate=[^;]+", "", normalized, flags=re.IGNORECASE
            )
    elif chosen and "DRIVER=" not in normalized.upper():
        normalized = f"DRIVER={{{chosen}}};{normalized}"
    if chosen != "SQL Server" and "ENCRYPT=" not in normalized.upper():
        normalized += ";Encrypt=yes;TrustServerCertificate=no;Connection Timeout=15;"
    return normalized


def ensure_session_turn_schema(conn_str: str) -> None:
    """Execute additive idempotent DDL to ensure dbo.session_turn exists."""
    if not conn_str:
        raise ValueError("SQL connection string is required for migration.")
    normalized = normalize_sql_conn_str(conn_str)
    with pyodbc.connect(normalized, timeout=20) as conn:
        cur = conn.cursor()
        cur.execute(SESSION_TURN_DDL)
        conn.commit()
    logger.info("Schema dbo.session_turn verified/created successfully.")
