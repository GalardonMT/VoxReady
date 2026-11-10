"""Additive, idempotent Azure SQL schema for the master labeling queue.

This module contains schema only. It never creates labeling cases, backfills
historical reports, or mutates existing sessions and reports. The caller must
run ``migrate`` inside the schema transaction and ``sp_getapplock`` used by
``scripts/prepare_azure_database.py``.
"""


LABELING_LEGACY_UPGRADE_STEPS = (
    """
IF OBJECT_ID(N'dbo.labeling_case', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.labeling_case', N'client_id') IS NULL
BEGIN
    IF OBJECT_ID(N'dbo.labeling_case_legacy_v1', N'U') IS NOT NULL
        THROW 51010,'Ya existe dbo.labeling_case_legacy_v1; se requiere revisión manual.',1;
    EXEC sys.sp_rename N'dbo.labeling_case', N'labeling_case_legacy_v1';
END;
""",
    """
IF OBJECT_ID(N'dbo.labeling_correction', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.labeling_correction', N'corrected_by') IS NOT NULL
BEGIN
    IF OBJECT_ID(N'dbo.labeling_correction_legacy_v1', N'U') IS NOT NULL
        THROW 51011,'Ya existe dbo.labeling_correction_legacy_v1; se requiere revisión manual.',1;
    EXEC sys.sp_rename N'dbo.labeling_correction', N'labeling_correction_legacy_v1';
END;
""",
)


LABELING_TABLE_STEPS = (
    """
IF OBJECT_ID(N'dbo.labeling_case', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.labeling_case (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_labeling_case PRIMARY KEY,
        case_number BIGINT IDENTITY(1,1) NOT NULL,
        client_id UNIQUEIDENTIFIER NOT NULL,
        session_id UNIQUEIDENTIFIER NOT NULL,
        report_id UNIQUEIDENTIFIER NOT NULL,
        analysis_job_id UNIQUEIDENTIFIER NOT NULL,
        rubric_version_id UNIQUEIDENTIFIER NOT NULL,
        session_finished_at DATETIME2(3) NOT NULL,
        queue_reason NVARCHAR(20) NOT NULL,
        reason_detail_json NVARCHAR(4000) NOT NULL,
        ai_snapshot_json NVARCHAR(MAX) NOT NULL,
        snapshot_schema_version SMALLINT NOT NULL,
        source_status NVARCHAR(20) NOT NULL,
        recording_evidence_path NVARCHAR(1024) NULL,
        recording_version_id NVARCHAR(255) NULL,
        recording_sha256 BINARY(32) NULL,
        recording_etag NVARCHAR(255) NULL,
        recording_content_type NVARCHAR(100) NULL,
        recording_duration_seconds DECIMAL(12,3) NULL,
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_labeling_case_status DEFAULT 'pending',
        lock_owner_id UNIQUEIDENTIFIER NULL,
        lock_token_hash BINARY(32) NULL,
        lock_acquired_at DATETIME2(3) NULL,
        lock_expires_at DATETIME2(3) NULL,
        lease_generation BIGINT NOT NULL CONSTRAINT DF_labeling_case_lease_generation DEFAULT 0,
        content_revision BIGINT NOT NULL CONSTRAINT DF_labeling_case_content_revision DEFAULT 1,
        resolved_by UNIQUEIDENTIFIER NULL,
        resolved_at DATETIME2(3) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_labeling_case_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_labeling_case_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_labeling_case_queue_reason
            CHECK (queue_reason IN ('critical','borderline','disparity','routine')),
        CONSTRAINT CK_labeling_case_source_status
            CHECK (source_status IN ('complete','partial','ambiguous')),
        CONSTRAINT CK_labeling_case_status
            CHECK (status IN ('pending','reviewed')),
        CONSTRAINT CK_labeling_case_reason_json CHECK (ISJSON(reason_detail_json)=1),
        CONSTRAINT CK_labeling_case_snapshot_json CHECK (ISJSON(ai_snapshot_json)=1),
        CONSTRAINT CK_labeling_case_snapshot_version CHECK (snapshot_schema_version>0),
        CONSTRAINT CK_labeling_case_revisions
            CHECK (lease_generation>=0 AND content_revision>0),
        CONSTRAINT CK_labeling_case_recording_duration
            CHECK (recording_duration_seconds IS NULL OR recording_duration_seconds>=0),
        CONSTRAINT CK_labeling_case_lease_shape CHECK (
            (lock_owner_id IS NULL AND lock_token_hash IS NULL
             AND lock_acquired_at IS NULL AND lock_expires_at IS NULL)
            OR
            (lock_owner_id IS NOT NULL AND lock_token_hash IS NOT NULL
             AND lock_acquired_at IS NOT NULL AND lock_expires_at>lock_acquired_at)
        ),
        CONSTRAINT CK_labeling_case_resolution_shape CHECK (
            (status='pending' AND resolved_by IS NULL AND resolved_at IS NULL)
            OR
            (status='reviewed' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)
        ),
        CONSTRAINT CK_labeling_case_complete_evidence CHECK (
            source_status<>'complete'
            OR
            (recording_evidence_path IS NOT NULL
             AND recording_sha256 IS NOT NULL
             AND recording_etag IS NOT NULL
             AND recording_content_type IS NOT NULL
             AND LEN(LTRIM(RTRIM(recording_evidence_path)))>0
             AND LEN(LTRIM(RTRIM(recording_etag)))>0
             AND LEN(LTRIM(RTRIM(recording_content_type)))>0)
        )
    );
END;
""",
    """
IF OBJECT_ID(N'dbo.labeling_review', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.labeling_review (
        id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_labeling_review PRIMARY KEY,
        labeling_case_id UNIQUEIDENTIFIER NOT NULL,
        reviewer_id UNIQUEIDENTIFIER NOT NULL,
        review_no INT NOT NULL,
        overall_comment NVARCHAR(4000) NOT NULL,
        supersedes_review_id UNIQUEIDENTIFIER NULL,
        is_current BIT NOT NULL CONSTRAINT DF_labeling_review_is_current DEFAULT 1,
        idempotency_key UNIQUEIDENTIFIER NOT NULL,
        request_hash BINARY(32) NOT NULL,
        submitted_at DATETIME2(3) NOT NULL CONSTRAINT DF_labeling_review_submitted_at DEFAULT SYSUTCDATETIME(),
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_labeling_review_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_labeling_review_number CHECK (review_no>0),
        CONSTRAINT CK_labeling_review_comment CHECK (LEN(LTRIM(RTRIM(overall_comment)))>0),
        CONSTRAINT CK_labeling_review_supersedes CHECK (
            supersedes_review_id IS NULL OR supersedes_review_id<>id
        )
    );
END;
""",
    """
IF OBJECT_ID(N'dbo.labeling_rubric_correction', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.labeling_rubric_correction (
        review_id UNIQUEIDENTIFIER NOT NULL,
        rubric_area_id UNIQUEIDENTIFIER NOT NULL,
        ai_value DECIMAL(6,2) NOT NULL,
        corrected_value DECIMAL(6,2) NOT NULL,
        comment NVARCHAR(2000) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_labeling_rubric_correction_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_labeling_rubric_correction PRIMARY KEY (review_id,rubric_area_id),
        CONSTRAINT CK_labeling_rubric_correction_ai CHECK (ai_value BETWEEN 0 AND 100),
        CONSTRAINT CK_labeling_rubric_correction_value CHECK (corrected_value BETWEEN 0 AND 100),
        CONSTRAINT CK_labeling_rubric_correction_comment CHECK (
            corrected_value=ai_value
            OR (comment IS NOT NULL AND LEN(LTRIM(RTRIM(comment)))>0)
        )
    );
END;
""",
    """
IF OBJECT_ID(N'dbo.labeling_metric_correction', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.labeling_metric_correction (
        review_id UNIQUEIDENTIFIER NOT NULL,
        metric_key NVARCHAR(80) NOT NULL,
        mapping_version SMALLINT NOT NULL,
        unit NVARCHAR(30) NOT NULL,
        ai_value DECIMAL(19,6) NOT NULL,
        corrected_value DECIMAL(19,6) NOT NULL,
        comment NVARCHAR(2000) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_labeling_metric_correction_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_labeling_metric_correction PRIMARY KEY (review_id,metric_key),
        CONSTRAINT CK_labeling_metric_correction_mapping CHECK (mapping_version>0),
        CONSTRAINT CK_labeling_metric_correction_unit CHECK (LEN(LTRIM(RTRIM(unit)))>0),
        CONSTRAINT CK_labeling_metric_correction_comment CHECK (
            corrected_value=ai_value
            OR (comment IS NOT NULL AND LEN(LTRIM(RTRIM(comment)))>0)
        )
    );
END;
""",
)


LABELING_PARENT_INDEX_STEPS = (
    """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.session') AND name=N'UQ_session_labeling_identity')
    CREATE UNIQUE INDEX UQ_session_labeling_identity ON dbo.session(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.analysis_job') AND name=N'UQ_analysis_job_labeling_identity')
    CREATE UNIQUE INDEX UQ_analysis_job_labeling_identity
        ON dbo.analysis_job(id,session_id,rubric_version_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.report') AND name=N'UQ_report_labeling_identity')
    CREATE UNIQUE INDEX UQ_report_labeling_identity
        ON dbo.report(id,session_id,analysis_job_id,rubric_version_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.report') AND name=N'UQ_report_labeling_current')
    CREATE UNIQUE INDEX UQ_report_labeling_current
        ON dbo.report(session_id) WHERE is_current=1;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.report') AND name=N'UQ_report_labeling_version')
    CREATE UNIQUE INDEX UQ_report_labeling_version
        ON dbo.report(session_id,version_no);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.analysis_pipeline_result') AND name=N'UQ_analysis_pipeline_result_fusion')
    CREATE UNIQUE INDEX UQ_analysis_pipeline_result_fusion
        ON dbo.analysis_pipeline_result(analysis_job_id) WHERE pipeline=N'fusion';
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'UQ_labeling_review_identity')
    CREATE UNIQUE INDEX UQ_labeling_review_identity
        ON dbo.labeling_review(id,labeling_case_id);
""",
)


LABELING_FOREIGN_KEY_STEPS = (
    """
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_client')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_client
        FOREIGN KEY (client_id) REFERENCES dbo.client(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_session_client')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_session_client
        FOREIGN KEY (session_id,client_id) REFERENCES dbo.session(id,client_id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_job_identity')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_job_identity
        FOREIGN KEY (analysis_job_id,session_id,rubric_version_id)
        REFERENCES dbo.analysis_job(id,session_id,rubric_version_id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_report_identity')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_report_identity
        FOREIGN KEY (report_id,session_id,analysis_job_id,rubric_version_id)
        REFERENCES dbo.report(id,session_id,analysis_job_id,rubric_version_id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_rubric_version')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_rubric_version
        FOREIGN KEY (rubric_version_id) REFERENCES dbo.rubric_version(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_lock_owner')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_lock_owner
        FOREIGN KEY (lock_owner_id) REFERENCES dbo.app_user(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'FK_labeling_case_resolved_by')
    ALTER TABLE dbo.labeling_case WITH CHECK ADD CONSTRAINT FK_labeling_case_resolved_by
        FOREIGN KEY (resolved_by) REFERENCES dbo.app_user(id);
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'FK_labeling_review_case')
    ALTER TABLE dbo.labeling_review WITH CHECK ADD CONSTRAINT FK_labeling_review_case
        FOREIGN KEY (labeling_case_id) REFERENCES dbo.labeling_case(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'FK_labeling_review_reviewer')
    ALTER TABLE dbo.labeling_review WITH CHECK ADD CONSTRAINT FK_labeling_review_reviewer
        FOREIGN KEY (reviewer_id) REFERENCES dbo.app_user(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'FK_labeling_review_supersedes')
    ALTER TABLE dbo.labeling_review WITH CHECK ADD CONSTRAINT FK_labeling_review_supersedes
        FOREIGN KEY (supersedes_review_id,labeling_case_id)
        REFERENCES dbo.labeling_review(id,labeling_case_id);
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_rubric_correction') AND name=N'FK_labeling_rubric_correction_review')
    ALTER TABLE dbo.labeling_rubric_correction WITH CHECK ADD CONSTRAINT FK_labeling_rubric_correction_review
        FOREIGN KEY (review_id) REFERENCES dbo.labeling_review(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_rubric_correction') AND name=N'FK_labeling_rubric_correction_area')
    ALTER TABLE dbo.labeling_rubric_correction WITH CHECK ADD CONSTRAINT FK_labeling_rubric_correction_area
        FOREIGN KEY (rubric_area_id) REFERENCES dbo.rubric_area(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_metric_correction') AND name=N'FK_labeling_metric_correction_review')
    ALTER TABLE dbo.labeling_metric_correction WITH CHECK ADD CONSTRAINT FK_labeling_metric_correction_review
        FOREIGN KEY (review_id) REFERENCES dbo.labeling_review(id);
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'dbo.labeling_metric_correction') AND name=N'FK_labeling_metric_correction_definition')
    ALTER TABLE dbo.labeling_metric_correction WITH CHECK ADD CONSTRAINT FK_labeling_metric_correction_definition
        FOREIGN KEY (metric_key) REFERENCES dbo.rubric_metric_definition(metric_key);
""",
)


LABELING_INDEX_STEPS = (
    """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'UQ_labeling_case_report')
    CREATE UNIQUE INDEX UQ_labeling_case_report ON dbo.labeling_case(report_id);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'UQ_labeling_case_number')
    CREATE UNIQUE INDEX UQ_labeling_case_number ON dbo.labeling_case(case_number);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'IX_labeling_case_queue')
    CREATE INDEX IX_labeling_case_queue
        ON dbo.labeling_case(status,session_finished_at DESC,id DESC)
        INCLUDE (queue_reason,client_id,report_id,lock_owner_id,lock_expires_at);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_case') AND name=N'IX_labeling_case_lease')
    CREATE INDEX IX_labeling_case_lease
        ON dbo.labeling_case(status,lock_expires_at)
        INCLUDE (lock_owner_id,lease_generation,content_revision);
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'UQ_labeling_review_case_number')
    CREATE UNIQUE INDEX UQ_labeling_review_case_number
        ON dbo.labeling_review(labeling_case_id,review_no);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'UQ_labeling_review_idempotency')
    CREATE UNIQUE INDEX UQ_labeling_review_idempotency
        ON dbo.labeling_review(labeling_case_id,idempotency_key);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'UQ_labeling_review_current')
    CREATE UNIQUE INDEX UQ_labeling_review_current
        ON dbo.labeling_review(labeling_case_id)
        WHERE is_current=1;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_review') AND name=N'IX_labeling_review_recent')
    CREATE INDEX IX_labeling_review_recent
        ON dbo.labeling_review(submitted_at DESC,id DESC)
        INCLUDE (labeling_case_id,reviewer_id,review_no,is_current);
""",
    """
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_rubric_correction') AND name=N'IX_labeling_rubric_correction_area')
    CREATE INDEX IX_labeling_rubric_correction_area
        ON dbo.labeling_rubric_correction(rubric_area_id,review_id)
        INCLUDE (ai_value,corrected_value);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'dbo.labeling_metric_correction') AND name=N'IX_labeling_metric_correction_metric')
    CREATE INDEX IX_labeling_metric_correction_metric
        ON dbo.labeling_metric_correction(metric_key,mapping_version,unit,review_id)
        INCLUDE (ai_value,corrected_value);
""",
)


LABELING_SCHEMA_STEPS = (
    LABELING_LEGACY_UPGRADE_STEPS
    + LABELING_TABLE_STEPS
    + LABELING_PARENT_INDEX_STEPS
    + LABELING_FOREIGN_KEY_STEPS
    + LABELING_INDEX_STEPS
)


REQUIRED_TABLE_COLUMNS = {
    "labeling_case": {
        "id",
        "case_number",
        "client_id",
        "session_id",
        "report_id",
        "analysis_job_id",
        "rubric_version_id",
        "session_finished_at",
        "queue_reason",
        "reason_detail_json",
        "ai_snapshot_json",
        "snapshot_schema_version",
        "source_status",
        "status",
        "lease_generation",
        "content_revision",
        "created_at",
        "updated_at",
    },
    "labeling_review": {
        "id",
        "labeling_case_id",
        "reviewer_id",
        "review_no",
        "overall_comment",
        "is_current",
        "idempotency_key",
        "request_hash",
        "submitted_at",
    },
    "labeling_rubric_correction": {
        "review_id",
        "rubric_area_id",
        "ai_value",
        "corrected_value",
        "comment",
    },
    "labeling_metric_correction": {
        "review_id",
        "metric_key",
        "mapping_version",
        "unit",
        "ai_value",
        "corrected_value",
        "comment",
    },
}

REQUIRED_INDEXES = {
    "session": {
        "UQ_session_labeling_identity": True,
    },
    "analysis_job": {
        "UQ_analysis_job_labeling_identity": True,
    },
    "report": {
        "UQ_report_labeling_identity": True,
        "UQ_report_labeling_current": True,
        "UQ_report_labeling_version": True,
    },
    "analysis_pipeline_result": {
        "UQ_analysis_pipeline_result_fusion": True,
    },
    "labeling_case": {
        "UQ_labeling_case_report": True,
        "UQ_labeling_case_number": True,
        "IX_labeling_case_queue": False,
        "IX_labeling_case_lease": False,
    },
    "labeling_review": {
        "UQ_labeling_review_identity": True,
        "UQ_labeling_review_case_number": True,
        "UQ_labeling_review_idempotency": True,
        "UQ_labeling_review_current": True,
        "IX_labeling_review_recent": False,
    },
    "labeling_rubric_correction": {
        "IX_labeling_rubric_correction_area": False,
    },
    "labeling_metric_correction": {
        "IX_labeling_metric_correction_metric": False,
    },
}

REQUIRED_FOREIGN_KEYS = {
    "FK_labeling_case_client",
    "FK_labeling_case_session_client",
    "FK_labeling_case_job_identity",
    "FK_labeling_case_report_identity",
    "FK_labeling_case_rubric_version",
    "FK_labeling_case_lock_owner",
    "FK_labeling_case_resolved_by",
    "FK_labeling_review_case",
    "FK_labeling_review_reviewer",
    "FK_labeling_review_supersedes",
    "FK_labeling_rubric_correction_review",
    "FK_labeling_rubric_correction_area",
    "FK_labeling_metric_correction_review",
    "FK_labeling_metric_correction_definition",
}

REQUIRED_CHECKS = {
    "CK_labeling_case_queue_reason",
    "CK_labeling_case_source_status",
    "CK_labeling_case_status",
    "CK_labeling_case_reason_json",
    "CK_labeling_case_snapshot_json",
    "CK_labeling_case_snapshot_version",
    "CK_labeling_case_revisions",
    "CK_labeling_case_recording_duration",
    "CK_labeling_case_lease_shape",
    "CK_labeling_case_resolution_shape",
    "CK_labeling_case_complete_evidence",
    "CK_labeling_review_number",
    "CK_labeling_review_comment",
    "CK_labeling_review_supersedes",
    "CK_labeling_rubric_correction_ai",
    "CK_labeling_rubric_correction_value",
    "CK_labeling_rubric_correction_comment",
    "CK_labeling_metric_correction_mapping",
    "CK_labeling_metric_correction_unit",
    "CK_labeling_metric_correction_comment",
}


def migrate(cursor):
    """Create the labeling schema inside the caller-owned transaction and lock."""
    for step in LABELING_SCHEMA_STEPS:
        cursor.execute(step)


def verify(cursor, error_type=RuntimeError):
    """Verify the labeling schema and stored-row invariants without writes."""
    for table, required_columns in REQUIRED_TABLE_COLUMNS.items():
        cursor.execute(
            """SELECT c.name
                 FROM sys.columns AS c
                WHERE c.object_id=OBJECT_ID(?)""",
            f"dbo.{table}",
        )
        actual = {str(row[0]).lower() for row in cursor.fetchall()}
        missing = sorted(required_columns - actual)
        if missing:
            raise error_type(
                f"Faltan columnas de dbo.{table}: {', '.join(missing)}."
            )

    for table, required_indexes in REQUIRED_INDEXES.items():
        cursor.execute(
            """SELECT i.name,i.is_unique,i.is_disabled,i.has_filter,i.filter_definition
                 FROM sys.indexes AS i
                WHERE i.object_id=OBJECT_ID(?) AND i.name IS NOT NULL""",
            f"dbo.{table}",
        )
        actual = {
            str(row[0]): (
                bool(row[1]),
                bool(row[2]),
                bool(row[3]),
                str(row[4] or "")
                .lower()
                .replace(" ", "")
                .replace("[", "")
                .replace("]", "")
                .replace("(", "")
                .replace(")", ""),
            )
            for row in cursor.fetchall()
        }
        for name, unique in required_indexes.items():
            row = actual.get(name)
            if not row or row[0] != unique or row[1]:
                raise error_type(f"Falta o no coincide el índice activo {name}.")
        required_filters = {
            ("report", "UQ_report_labeling_current"): "is_current=1",
            (
                "analysis_pipeline_result",
                "UQ_analysis_pipeline_result_fusion",
            ): "pipeline=n'fusion'",
            ("labeling_review", "UQ_labeling_review_current"): "is_current=1",
        }
        for (filter_table, filter_name), expected_filter in required_filters.items():
            if table != filter_table:
                continue
            index = actual.get(filter_name)
            if not index or not index[2] or expected_filter not in index[3]:
                raise error_type(
                    f"{filter_name} debe conservar su filtro {expected_filter}."
                )

    cursor.execute(
        """SELECT fk.name,fk.is_disabled,fk.is_not_trusted
             FROM sys.foreign_keys AS fk
            WHERE fk.name LIKE N'FK_labeling[_]%'"""
    )
    foreign_keys = {
        str(row[0]): (bool(row[1]), bool(row[2])) for row in cursor.fetchall()
    }
    for name in REQUIRED_FOREIGN_KEYS:
        state = foreign_keys.get(name)
        if not state or state[0] or state[1]:
            raise error_type(f"Falta la clave foránea activa y confiable {name}.")

    cursor.execute(
        """SELECT cc.name,cc.is_disabled,cc.is_not_trusted
             FROM sys.check_constraints AS cc
            WHERE cc.name LIKE N'CK_labeling[_]%'"""
    )
    checks = {
        str(row[0]): (bool(row[1]), bool(row[2])) for row in cursor.fetchall()
    }
    for name in REQUIRED_CHECKS:
        state = checks.get(name)
        if not state or state[0] or state[1]:
            raise error_type(f"Falta la restricción activa y confiable {name}.")

    cursor.execute(
        """SELECT
               (SELECT COUNT_BIG(*) FROM (
                    SELECT report_id FROM dbo.labeling_case
                    GROUP BY report_id HAVING COUNT_BIG(*)>1
                ) AS duplicated_cases),
               (SELECT COUNT_BIG(*) FROM (
                    SELECT labeling_case_id FROM dbo.labeling_review
                    WHERE is_current=1
                    GROUP BY labeling_case_id HAVING COUNT_BIG(*)>1
                ) AS duplicated_current_reviews),
               (SELECT COUNT_BIG(*)
                  FROM dbo.labeling_case AS lc
                  LEFT JOIN dbo.report AS r
                    ON r.id=lc.report_id
                   AND r.session_id=lc.session_id
                   AND r.analysis_job_id=lc.analysis_job_id
                   AND r.rubric_version_id=lc.rubric_version_id
                 WHERE r.id IS NULL)"""
    )
    integrity = cursor.fetchone()
    if not integrity or any(int(value or 0) for value in integrity):
        raise error_type(
            "La integridad de casos, revisión vigente o relación con report no coincide."
        )

    return {
        "tables": len(REQUIRED_TABLE_COLUMNS),
        "indexes": sum(len(indexes) for indexes in REQUIRED_INDEXES.values()),
        "foreignKeys": len(REQUIRED_FOREIGN_KEYS),
        "checks": len(REQUIRED_CHECKS),
    }
