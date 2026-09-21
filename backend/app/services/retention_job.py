"""Periodic retention job: purge/archive recordings per client policy."""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app import db as db_module
from app.config import Settings
from app.core.storage import get_storage
from app.models.privacy import RetentionPolicy
from app.models.recording import Recording
from app.models.sessions import PracticeSession
from app.services.helpers import audit
from app.utils import utcnow

logger = logging.getLogger("voxready.retention")

ARCHIVE_AFTER_DAYS = 180  # move to archive tier after 6 months


class RetentionJob:
    """Asyncio periodic task started with the app lifespan."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="retention-job")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.retention_job_interval_seconds)
            try:
                async with db_module.new_session() as db:
                    result = await run_retention_once(db)
                    await db.commit()
                    if result["purged"] or result["archived"]:
                        logger.info("Retención: %s", result)
            except Exception:  # noqa: BLE001
                logger.exception("Error en el job de retención")


async def run_retention_once(db) -> dict:
    """Apply each client's current policy. Returns purge/archive counts."""
    storage = get_storage()
    now = utcnow()
    purged = archived = 0
    policies = (
        await db.scalars(
            select(RetentionPolicy).where(RetentionPolicy.is_current.is_(True))
        )
    ).all()
    for policy in policies:
        recordings = (
            await db.scalars(
                select(Recording)
                .join(PracticeSession, Recording.session_id == PracticeSession.id)
                .where(
                    PracticeSession.client_id == policy.client_id,
                    Recording.status.in_(["available", "archived"]),
                )
            )
        ).all()
        for recording in recordings:
            age_days = (now - recording.created_at).days
            should_purge = policy.keep == "metrics_only" or (
                policy.term_days is not None and age_days > policy.term_days
            )
            if should_purge:
                recording.status = "deleted"
                recording.deleted_at = now
                storage.delete(recording.blob_path)
                audit(
                    db,
                    "retention_expired",
                    client_id=policy.client_id,
                    entity_type="recording",
                    entity_id=recording.id,
                    detail={
                        "policyVersion": policy.version_label,
                        "blobPath": recording.blob_path,
                    },
                )
                purged += 1
            elif (
                policy.keep == "full_recording"
                and recording.status == "available"
                and age_days > ARCHIVE_AFTER_DAYS
            ):
                recording.status = "archived"
                recording.storage_tier = "archive"
                recording.archived_at = now
                archived += 1
    return {"purged": purged, "archived": archived}
