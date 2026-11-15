"""Actualizacion explicita del estado de un job de analisis."""

import logging
from typing import Optional


logger = logging.getLogger("analysis-worker.job-status")


def update_analysis_job_status(
    db_service,
    job_id: str,
    status: str,
    failure_reason: Optional[str] = None,
    *,
    best_effort: bool = False,
) -> bool:
    """Actualiza el job; solo el cleanup de errores puede ser best-effort."""
    if status not in {"completed", "failed"}:
        raise ValueError("El estado del job debe ser completed o failed.")

    try:
        with db_service.get_connection() as connection:
            cursor = connection.cursor()
            if status == "completed":
                cursor.execute(
                    """
                    UPDATE dbo.analysis_job
                    SET status = 'completed',
                        completed_at = COALESCE(completed_at, SYSUTCDATETIME()),
                        failure_reason = NULL, updated_at = SYSUTCDATETIME()
                    WHERE id = ?
                    """,
                    job_id,
                )
            else:
                cursor.execute(
                    """
                    UPDATE dbo.analysis_job
                    SET status = 'failed', failure_reason = ?,
                        completed_at = NULL, updated_at = SYSUTCDATETIME()
                    WHERE id = ? AND status <> 'completed'
                    """,
                    (str(failure_reason)[:500] if failure_reason else None, job_id),
                )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"analysis_job {job_id} no existe o no se actualizó exactamente una vez."
                )
            connection.commit()
        return True
    except Exception as error:
        if not best_effort:
            raise
        logger.warning(
            "No se pudo actualizar analysis_job %s a %s durante el cleanup: %s",
            job_id,
            status,
            error,
        )
        return False
