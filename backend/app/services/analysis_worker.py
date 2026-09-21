"""In-process asyncio worker running the (stubbed) multimodal analysis.

Pipelines are deterministic, interchangeable stubs: each one sleeps briefly,
marks progress and produces plausible aggregates. Swap `process_analysis`
internals for real providers (Azure AI Speech, Video Indexer, OpenAI) later.
"""
import asyncio
import hashlib
import logging
import uuid

from sqlalchemy import func, select

from app import db as db_module
from app.config import Settings
from app.core.webhooks import build_event_payload, fire_and_forget
from app.models.analysis import (
    AnalysisJob,
    AnalysisPipelineResult,
    AreaScore,
    Report,
)
from app.models.labeling import LabelingCase
from app.models.progress import Microlesson, Recommendation, UserAreaProgress
from app.models.rubric import RubricArea
from app.models.sessions import PracticeSession
from app.utils import PIPELINES, utcnow

logger = logging.getLogger("voxready.analysis")

AREA_LABELS = {
    "expression": "expresión y lenguaje corporal",
    "voice": "voz y prosodia",
    "coherence": "coherencia del mensaje",
    "empathy": "empatía",
}

AREA_TO_LESSON_TAG = {
    "expression": "body-language",
    "voice": "voice-control",
    "coherence": "bridging",
    "empathy": "empathy",
}


def _hash_int(*parts: str) -> int:
    return int(hashlib.md5(":".join(parts).encode()).hexdigest()[:8], 16)


def _stub_score(session_id: uuid.UUID, area_key: str) -> int:
    """Deterministic plausible area score (40-95)."""
    return 40 + _hash_int(str(session_id), area_key) % 56


def _stub_confidence(session_id: uuid.UUID) -> float:
    """Deterministic simulated confidence (0.40-0.99)."""
    return 0.4 + (_hash_int("conf", str(session_id)) % 60) / 100


def _stub_summary(pipeline: str, session_id: uuid.UUID) -> dict:
    base = _hash_int(pipeline, str(session_id))
    if pipeline == "voice":
        return {
            "fillerWordsPerMinute": base % 8,
            "averageWpm": 120 + base % 40,
            "toneVariability": round(0.4 + (base % 50) / 100, 2),
        }
    if pipeline == "image":
        return {
            "eyeContactPct": 55 + base % 40,
            "openPosturePct": 50 + base % 45,
            "distractingGestures": base % 5,
        }
    if pipeline == "content":
        return {
            "keyMessagesCovered": 1 + base % 3,
            "redLinesCrossed": base % 2,
            "bridgingAttempts": base % 4,
        }
    return {
        "verbalNonverbalAlignment": round(0.5 + (base % 45) / 100, 2),
        "empathySignals": base % 6,
    }


class AnalysisWorker:
    """Asyncio in-process queue worker started with the app lifespan."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="analysis-worker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def enqueue(self, job_id: uuid.UUID) -> None:
        self.queue.put_nowait(job_id)

    async def _loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await process_analysis(self.settings, job_id)
            except Exception:  # noqa: BLE001 - last-resort guard
                logger.exception("Error procesando analysis_job %s", job_id)
            finally:
                self.queue.task_done()


async def _mark_failed(settings: Settings, job_id: uuid.UUID, reason: str) -> None:
    async with db_module.new_session() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.failure_reason = reason[:500]
        job.completed_at = utcnow()
        session = await db.get(PracticeSession, job.session_id)
        if session is not None:
            session.status = "failed"
        await db.commit()
        fire_and_forget(
            settings,
            build_event_payload(
                "session.analysis.failed",
                job.session_id,
                job.id,
                "failed",
                False,
                failure_reason=job.failure_reason,
            ),
        )


async def process_analysis(settings: Settings, job_id: uuid.UUID) -> None:
    """Run the 4 stub pipelines and materialize report + side effects."""
    try:
        await _process(settings, job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo irrecuperable en análisis %s", job_id)
        await _mark_failed(settings, job_id, f"Error interno del pipeline: {exc!r}")


async def _process(settings: Settings, job_id: uuid.UUID) -> None:
    async with db_module.new_session() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        session = await db.get(PracticeSession, job.session_id)
        areas = list(
            (
                await db.scalars(
                    select(RubricArea)
                    .where(RubricArea.rubric_version_id == job.rubric_version_id)
                    .order_by(RubricArea.sort_order)
                )
            ).all()
        )
        job.status = "running"
        job.started_at = utcnow()
        await db.commit()

        # 1) Pipelines (stubs) with observable progress.
        for pipeline in PIPELINES:
            await asyncio.sleep(settings.analysis_step_seconds)
            row = await db.scalar(
                select(AnalysisPipelineResult).where(
                    AnalysisPipelineResult.analysis_job_id == job.id,
                    AnalysisPipelineResult.pipeline == pipeline,
                )
            )
            if row is not None:
                row.status = "done"
                row.summary_json = _stub_summary(pipeline, session.id)
                await db.commit()

        # 2) Scores per rubric area (data-driven) and weighted overall.
        scores = {area: _stub_score(session.id, area.area_key) for area in areas}
        total_weight = sum(area.weight for area in areas) or 100
        overall = round(
            sum(scores[area] * area.weight for area in areas) / total_weight
        )
        confidence = _stub_confidence(session.id)

        # 3) Previous first values (for progress delta) before inserting.
        first_values: dict[uuid.UUID, int | None] = {}
        for area in areas:
            first_values[area.id] = await db.scalar(
                select(AreaScore.value)
                .join(Report, AreaScore.report_id == Report.id)
                .join(PracticeSession, Report.session_id == PracticeSession.id)
                .where(
                    PracticeSession.user_id == session.user_id,
                    AreaScore.rubric_area_id == area.id,
                    Report.id.isnot(None),
                )
                .order_by(Report.generated_at.asc())
                .limit(1)
            )

        # 4) Report (new version, previous ones become non-current).
        previous_reports = (
            await db.scalars(
                select(Report).where(
                    Report.session_id == session.id, Report.is_current.is_(True)
                )
            )
        ).all()
        for previous in previous_reports:
            previous.is_current = False
        version_no = (
            await db.scalar(
                select(func.count(Report.id)).where(Report.session_id == session.id)
            )
            or 0
        ) + 1

        sorted_areas = sorted(areas, key=lambda a: scores[a])
        weakest, strongest = sorted_areas[0], sorted_areas[-1]
        report = Report(
            session_id=session.id,
            analysis_job_id=job.id,
            rubric_version_id=job.rubric_version_id,
            overall_score=overall,
            narrative_strengths=[
                f"Buen desempeño en {AREA_LABELS.get(strongest.area_key, strongest.name)} "
                f"({scores[strongest]}/100).",
                "Estructura clara de la respuesta y cierre con mensaje puente.",
            ],
            narrative_improvements=[
                f"Refuerza {AREA_LABELS.get(weakest.area_key, weakest.name)} "
                f"({scores[weakest]}/100) con la microlección sugerida.",
                "Reduce muletillas en las respuestas a preguntas hostiles.",
            ],
            cross_signal_observation=(
                "El lenguaje verbal expresó empatía, pero la señal no verbal "
                "fue neutra; alinear ambos canales aumenta la credibilidad."
            ),
            version_no=version_no,
            is_current=True,
            generated_at=utcnow(),
        )
        db.add(report)
        await db.flush()
        for area in areas:
            db.add(
                AreaScore(
                    report_id=report.id,
                    rubric_area_id=area.id,
                    value=scores[area],
                )
            )

        session.status = "completed"
        job.status = "completed"
        job.completed_at = utcnow()

        # 5) Denormalized per-area progress.
        for area in areas:
            progress = await db.scalar(
                select(UserAreaProgress).where(
                    UserAreaProgress.user_id == session.user_id,
                    UserAreaProgress.rubric_area_id == area.id,
                )
            )
            first = first_values[area.id]
            if progress is None:
                progress = UserAreaProgress(
                    user_id=session.user_id,
                    rubric_area_id=area.id,
                    sessions_count=0,
                )
                db.add(progress)
            progress.current_value = scores[area]
            progress.delta = scores[area] - first if first is not None else 0
            progress.sessions_count += 1
            progress.last_session_at = utcnow()

        # 6) Labeling case rules (low confidence / borderline / ~10% random).
        reason = None
        if confidence < 0.6:
            reason = "low_confidence"
        elif 45 <= overall <= 55:
            reason = "borderline"
        elif _hash_int("sample", str(session.id)) % 100 < settings.labeling_random_sample_rate:
            reason = "random"
        if reason is not None:
            existing_case = await db.scalar(
                select(LabelingCase).where(LabelingCase.session_id == session.id)
            )
            if existing_case is None:
                db.add(
                    LabelingCase(
                        session_id=session.id,
                        rubric_version_id=job.rubric_version_id,
                        reason=reason,
                        status="pending",
                    )
                )

        # 7) Actionable recommendation linked to a microlesson.
        tag = AREA_TO_LESSON_TAG.get(weakest.area_key)
        lesson = None
        if tag:
            lesson = await db.scalar(
                select(Microlesson)
                .where(
                    Microlesson.client_id == session.client_id,
                    Microlesson.topic_tag == tag,
                    Microlesson.status == "active",
                    Microlesson.is_deleted.is_(False),
                )
                .limit(1)
            )
        if lesson is None:
            lesson = await db.scalar(
                select(Microlesson)
                .where(
                    Microlesson.client_id == session.client_id,
                    Microlesson.status == "active",
                    Microlesson.is_deleted.is_(False),
                )
                .limit(1)
            )
        db.add(
            Recommendation(
                client_id=session.client_id,
                user_id=session.user_id,
                title=f"Refuerza {AREA_LABELS.get(weakest.area_key, weakest.name)}",
                detail=(
                    f"Tu puntaje más bajo fue {scores[weakest]}/100 en "
                    f"{AREA_LABELS.get(weakest.area_key, weakest.name)}. "
                    "Practica con la microlección vinculada antes de tu próxima sesión."
                ),
                microlesson_id=lesson.id if lesson else None,
                source="generated",
                status="active",
            )
        )

        await db.commit()

    # 8) Outgoing webhook (after commit, outside the session).
    fire_and_forget(
        settings,
        build_event_payload(
            "session.analysis.completed",
            session.id,
            job.id,
            "completed",
            True,
        ),
    )
