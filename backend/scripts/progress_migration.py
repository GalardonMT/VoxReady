"""DDL y backfill aditivos para la pantalla Mi Progreso.

El inicializador ejecuta cada elemento de ``PROGRESS_SCHEMA_STEPS`` como un
batch independiente para que Azure SQL recompile después de añadir
``schedule.session_id``. Todas las operaciones se ejecutan dentro de la
transacción y del bloqueo de aplicación de ``prepare_azure_database.py``.
"""

SCHEDULE_SESSION_COLUMN_DDL = """
IF COL_LENGTH(N'dbo.schedule', N'session_id') IS NULL
    ALTER TABLE dbo.schedule ADD session_id UNIQUEIDENTIFIER NULL;
"""

PROGRESS_CONSTRAINTS_AND_INDEXES_DDL = """
IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(N'dbo.schedule')
      AND referenced_object_id = OBJECT_ID(N'dbo.session')
      AND name = N'FK_schedule_session'
)
    ALTER TABLE dbo.schedule WITH CHECK
        ADD CONSTRAINT FK_schedule_session
        FOREIGN KEY (session_id) REFERENCES dbo.session(id);

IF EXISTS (
    SELECT 1
    FROM dbo.user_area_progress
    GROUP BY user_id, rubric_area_id
    HAVING COUNT_BIG(*) > 1
)
    THROW 51001,
          'dbo.user_area_progress contiene duplicados por user_id y rubric_area_id; no se creó el índice único.',
          1;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.user_area_progress')
      AND name = N'UQ_user_area_progress_user_area'
)
    CREATE UNIQUE INDEX UQ_user_area_progress_user_area
        ON dbo.user_area_progress(user_id, rubric_area_id);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.schedule')
      AND name = N'UQ_schedule_session'
)
    CREATE UNIQUE INDEX UQ_schedule_session
        ON dbo.schedule(session_id)
        WHERE session_id IS NOT NULL;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.schedule')
      AND name = N'IX_schedule_client_user_date'
)
    CREATE INDEX IX_schedule_client_user_date
        ON dbo.schedule(client_id, user_id, scheduled_date, status)
        INCLUDE (scenario_id, session_id, updated_at);
"""

PROGRESS_SCHEMA_STEPS = (
    SCHEDULE_SESSION_COLUMN_DDL,
    PROGRESS_CONSTRAINTS_AND_INDEXES_DDL,
)

# Forma concatenada para inspección, documentación y pruebas de contrato.
PROGRESS_SCHEMA_DDL = "\n".join(PROGRESS_SCHEMA_STEPS)


USER_AREA_PROGRESS_BACKFILL_DML = """
;WITH current_reports AS (
    SELECT
        r.id,
        r.session_id,
        ROW_NUMBER() OVER (
            PARTITION BY r.session_id
            ORDER BY r.generated_at DESC, r.id DESC
        ) AS report_position
    FROM dbo.report AS r
    WHERE r.is_current = 1
),
ranked_area_scores AS (
    SELECT
        a.report_id,
        a.rubric_area_id,
        ra.area_key,
        a.value,
        ROW_NUMBER() OVER (
            PARTITION BY a.report_id, ra.area_key
            ORDER BY a.id DESC
        ) AS score_position
    FROM dbo.area_score AS a
    INNER JOIN dbo.rubric_area AS ra
        ON ra.id = a.rubric_area_id
),
scored_sessions AS (
    SELECT
        s.user_id,
        a.area_key,
        a.rubric_area_id,
        a.value,
        COALESCE(s.finished_at, s.updated_at, s.created_at) AS session_at,
        s.id AS session_id,
        ROW_NUMBER() OVER (
            PARTITION BY s.user_id, a.area_key
            ORDER BY COALESCE(s.finished_at, s.updated_at, s.created_at) DESC,
                     s.id DESC
        ) AS area_position,
        LEAD(a.value) OVER (
            PARTITION BY s.user_id, a.area_key
            ORDER BY COALESCE(s.finished_at, s.updated_at, s.created_at) DESC,
                     s.id DESC
        ) AS previous_value
    FROM dbo.session AS s
    INNER JOIN current_reports AS r
        ON r.session_id = s.id
       AND r.report_position = 1
    INNER JOIN ranked_area_scores AS a
        ON a.report_id = r.id
       AND a.score_position = 1
    WHERE s.status = N'completed'
      AND s.is_deleted = 0
),
session_totals AS (
    SELECT
        s.user_id,
        COUNT_BIG(DISTINCT s.id) AS sessions_count,
        MAX(COALESCE(s.finished_at, s.updated_at, s.created_at)) AS last_session_at
    FROM dbo.session AS s
    WHERE s.status = N'completed'
      AND s.is_deleted = 0
      AND EXISTS (
          SELECT 1
          FROM current_reports AS r
          WHERE r.session_id = s.id
            AND r.report_position = 1
      )
    GROUP BY s.user_id
),
latest_area_progress AS (
    SELECT
        scored.user_id,
        scored.rubric_area_id,
        scored.value AS current_value,
        CASE
            WHEN scored.previous_value IS NULL THEN NULL
            ELSE scored.value - scored.previous_value
        END AS delta_value,
        CONVERT(INT, totals.sessions_count) AS sessions_count,
        totals.last_session_at
    FROM scored_sessions AS scored
    INNER JOIN session_totals AS totals
        ON totals.user_id = scored.user_id
    WHERE scored.area_position = 1
)
MERGE dbo.user_area_progress WITH (HOLDLOCK) AS target
USING latest_area_progress AS source
   ON target.user_id = source.user_id
  AND target.rubric_area_id = source.rubric_area_id
WHEN MATCHED AND (
       ISNULL(target.current_value, -2147483648) <> ISNULL(source.current_value, -2147483648)
    OR ISNULL(target.[delta], -2147483648) <> ISNULL(source.delta_value, -2147483648)
    OR target.sessions_count <> source.sessions_count
    OR ISNULL(target.last_session_at, CONVERT(DATETIME2, '19000101', 112))
       <> ISNULL(source.last_session_at, CONVERT(DATETIME2, '19000101', 112))
)
    THEN UPDATE SET
        current_value = source.current_value,
        [delta] = source.delta_value,
        sessions_count = source.sessions_count,
        last_session_at = source.last_session_at,
        updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (
        id, user_id, rubric_area_id, current_value, [delta],
        sessions_count, last_session_at, created_at, updated_at
    )
    VALUES (
        NEWID(), source.user_id, source.rubric_area_id, source.current_value,
        source.delta_value, source.sessions_count, source.last_session_at,
        SYSUTCDATETIME(), SYSUTCDATETIME()
    );
"""
