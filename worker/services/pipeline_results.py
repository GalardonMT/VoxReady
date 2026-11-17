"""Persistencia idempotente de resultados intermedios del analisis."""

import json
import logging
import time
from typing import Any, Callable, Dict


logger = logging.getLogger("analysis-worker.pipeline-results")

_TRANSIENT_SQLSTATES = {"40001", "HYT00", "HYT01"}
_TRANSIENT_AZURE_SQL_CODES = {
    "40197",
    "40501",
    "40613",
    "49918",
    "49919",
    "49920",
}


def is_transient_sql_error(error: Exception) -> bool:
    """Reconoce solo fallas SQL que admiten un reintento seguro."""
    details = " ".join(str(item) for item in getattr(error, "args", ()) if item is not None)
    if not details:
        details = str(error)
    upper_details = details.upper()
    sqlstate = upper_details[:5]
    return (
        sqlstate.startswith("08")
        or sqlstate in _TRANSIENT_SQLSTATES
        or any(code in upper_details for code in _TRANSIENT_AZURE_SQL_CODES)
    )


def _insert_pipeline_result_once(cursor, job_id: str, pipeline: str, summary_json: str) -> None:
    # HOLDLOCK equivale a SERIALIZABLE: protege tambien la ausencia de la clave
    # durante la lectura/insercion y evita dos escrituras concurrentes.
    cursor.execute(
        """
        DECLARE @existing_count INT;
        SELECT @existing_count = COUNT(*)
        FROM dbo.analysis_pipeline_result WITH (UPDLOCK, HOLDLOCK)
        WHERE analysis_job_id = ? AND pipeline = ?;

        IF @existing_count > 1
            THROW 51001, 'Resultados duplicados para analysis_job_id y pipeline.', 1;

        IF @existing_count = 0
        BEGIN
            INSERT INTO dbo.analysis_pipeline_result (
                id, analysis_job_id, pipeline, status, summary_json, created_at, updated_at
            )
            VALUES (NEWID(), ?, ?, 'completed', ?, SYSUTCDATETIME(), SYSUTCDATETIME());
        END
        """,
        (job_id, pipeline, job_id, pipeline, summary_json),
    )


def _persist_once(db_service, job_id: str, results_map: Dict[str, Any]) -> None:
    with db_service.get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            IF @@TRANCOUNT = 0
                BEGIN TRANSACTION;

            DECLARE @lock_result INT;
            EXEC @lock_result = sys.sp_getapplock
                @Resource = ?,
                @LockMode = 'Exclusive',
                @LockOwner = 'Transaction',
                @LockTimeout = 10000;
            IF @lock_result < 0
                THROW 51002, 'No se pudo adquirir el lock del job.', 1;
            """,
            f"analysis_pipeline_result:{job_id}",
        )
        for pipeline, result in results_map.items():
            _insert_pipeline_result_once(
                cursor,
                job_id,
                pipeline,
                json.dumps(result, ensure_ascii=False),
            )
        connection.commit()


def persist_pipeline_results(
    db_service,
    job_id: str,
    results_map: Dict[str, Any],
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.25,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Persiste cada pipeline una vez por job, tolerando fallas SQL transitorias."""
    if max_attempts < 1:
        raise ValueError("max_attempts debe ser al menos 1")

    for attempt in range(1, max_attempts + 1):
        try:
            _persist_once(db_service, job_id, results_map)
            logger.info(
                "Trazabilidad de pipelines persistida para job %s (intento %s)",
                job_id,
                attempt,
            )
            return
        except Exception as error:
            if attempt >= max_attempts or not is_transient_sql_error(error):
                raise
            delay = retry_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Falla SQL transitoria al persistir pipelines del job %s; "
                "reintento %s/%s en %.2fs: %s",
                job_id,
                attempt + 1,
                max_attempts,
                delay,
                error,
            )
            sleep_fn(delay)
