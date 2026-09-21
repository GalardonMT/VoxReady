"""Master configuration endpoints: dashboard, rubric, labeling queue."""
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, pagination_params, to_uuid
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.core.storage import get_storage
from app.db import get_db
from app.models.analysis import AreaScore, Report
from app.models.identity import Client
from app.models.labeling import (
    AiHumanAgreementMetric,
    LabelingCase,
    LabelingCorrection,
)
from app.models.recording import Recording
from app.models.rubric import RubricArea, RubricDescriptor, RubricVersion
from app.models.sessions import PracticeSession
from app.schemas.master import ResolveCaseIn, RubricDraftIn, RubricPublishIn
from app.services.helpers import audit
from app.utils import iso, utcnow

router = APIRouter(tags=["master"])

BUCKETS = ["0-20", "21-40", "41-60", "61-80", "81-100"]


# ---------------------------------------------------------------- dashboard
@router.get("/master/dashboard")
async def master_dashboard(
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    active_clients = await db.scalar(
        select(func.count(Client.id)).where(
            Client.status == "active", Client.is_deleted.is_(False)
        )
    )
    sessions_this_week = await db.scalar(
        select(func.count(PracticeSession.id)).where(
            PracticeSession.created_at >= utcnow() - timedelta(days=7),
            PracticeSession.is_deleted.is_(False),
        )
    )
    review_queue_size = await db.scalar(
        select(func.count(LabelingCase.id)).where(LabelingCase.status == "pending")
    )

    # AI-human agreement: 1 - mean(|ai - corrected|)/100 over corrections,
    # falling back to the latest aggregated metric row.
    agreement = await db.scalar(
        select(
            1
            - func.avg(func.abs(LabelingCorrection.ai_value - LabelingCorrection.corrected_value))
            / 100.0
        )
    )
    if agreement is None:
        agreement = await db.scalar(
            select(AiHumanAgreementMetric.agreement)
            .order_by(AiHumanAgreementMetric.computed_at.desc())
            .limit(1)
        )
    agreement_value = round(float(agreement), 3) if agreement is not None else None

    counts = {bucket: 0 for bucket in BUCKETS}
    overall_rows = (
        await db.scalars(
            select(Report.overall_score).where(Report.is_current.is_(True))
        )
    ).all()
    for score in overall_rows:
        index = min(score // 20, 4)
        counts[BUCKETS[index]] += 1

    return {
        "activeClients": active_clients or 0,
        "sessionsThisWeek": sessions_this_week or 0,
        "reviewQueueSize": review_queue_size or 0,
        "aiHumanAgreement": agreement_value,
        "scoreDistribution": [
            {"bucket": bucket, "count": counts[bucket]} for bucket in BUCKETS
        ],
    }


# ------------------------------------------------------------------- rubric
def _serialize_rubric(
    version: RubricVersion, areas: list[tuple[RubricArea, dict[str, str]]]
) -> dict:
    return {
        "version": version.version_label,
        "status": version.status,
        "areas": [
            {
                "area": area.area_key,
                "name": area.name,
                "channel": area.channel,
                "criteria": area.criteria,
                "weight": area.weight,
                "descriptors": descriptors,
            }
            for area, descriptors in areas
        ],
        "languages": version.languages or [],
    }


async def _rubric_areas(
    db: AsyncSession, version: RubricVersion
) -> list[tuple[RubricArea, dict[str, str]]]:
    areas = list(
        (
            await db.scalars(
                select(RubricArea)
                .where(RubricArea.rubric_version_id == version.id)
                .order_by(RubricArea.sort_order)
            )
        ).all()
    )
    result = []
    for area in areas:
        descriptors = (
            await db.scalars(
                select(RubricDescriptor).where(
                    RubricDescriptor.rubric_area_id == area.id
                )
            )
        ).all()
        result.append((area, {d.level: d.description for d in descriptors}))
    return result


@router.get("/master/rubric")
async def get_rubric(
    version: str | None = Query(None),
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if version:
        rubric = await db.scalar(
            select(RubricVersion).where(RubricVersion.version_label == version)
        )
    else:
        rubric = await db.scalar(
            select(RubricVersion)
            .where(RubricVersion.status == "published")
            .order_by(RubricVersion.published_at.desc())
            .limit(1)
        )
    if rubric is None:
        raise AppError(404, "version_not_found", "La versión solicitada no existe.")
    return _serialize_rubric(rubric, await _rubric_areas(db, rubric))


def _next_draft_label(latest_label: str | None) -> str:
    if latest_label:
        match = re.match(r"v(\d+)\.(\d+)", latest_label)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            return f"v{major}.{minor + 1}-draft"
    return "v0.1-draft"


@router.put("/master/rubric")
async def put_rubric_draft(
    body: RubricDraftIn,
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if sum(area.weight for area in body.areas) != 100:
        raise AppError(
            400,
            "weights_sum_invalid",
            "La suma de los pesos de las áreas no es 100%.",
        )

    draft = await db.scalar(
        select(RubricVersion)
        .where(RubricVersion.status == "draft")
        .order_by(RubricVersion.updated_at.desc())
        .limit(1)
    )
    if draft is None:
        latest = await db.scalar(
            select(RubricVersion.version_label).order_by(
                RubricVersion.created_at.desc()
            )
        )
        draft = RubricVersion(
            version_label=_next_draft_label(latest),
            status="draft",
            created_by=principal.user_id,
        )
        db.add(draft)
        await db.flush()
    else:
        # Update existing draft in place: replace areas and descriptors.
        area_ids = (
            await db.scalars(
                select(RubricArea.id).where(
                    RubricArea.rubric_version_id == draft.id
                )
            )
        ).all()
        if area_ids:
            await db.execute(
                delete(RubricDescriptor).where(
                    RubricDescriptor.rubric_area_id.in_(area_ids)
                )
            )
            await db.execute(
                delete(RubricArea).where(RubricArea.rubric_version_id == draft.id)
            )

    draft.languages = list(body.languages)
    for index, area_in in enumerate(body.areas, start=1):
        area_key = re.sub(r"[^a-z0-9]+", "-", area_in.name.lower()).strip("-")[:30]
        area = RubricArea(
            rubric_version_id=draft.id,
            area_key=area_key or f"area-{index}",
            name=area_in.name,
            channel=area_in.channel,
            criteria=area_in.criteria,
            weight=area_in.weight,
            sort_order=index,
        )
        db.add(area)
        await db.flush()
        for level in ("high", "medium", "low"):
            if level in area_in.descriptors:
                db.add(
                    RubricDescriptor(
                        rubric_area_id=area.id,
                        level=level,
                        description=area_in.descriptors[level],
                    )
                )
    await db.commit()
    return {
        "version": draft.version_label,
        "status": "draft",
        "updatedAt": iso(draft.updated_at),
    }


@router.post("/master/rubric/publish")
async def publish_rubric(
    body: RubricPublishIn,
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rubric = await db.scalar(
        select(RubricVersion).where(RubricVersion.version_label == body.version)
    )
    if rubric is None:
        raise AppError(404, "version_not_found", "La versión no existe.")
    if rubric.status == "published":
        raise AppError(409, "already_published", "La versión ya estaba publicada.")
    rubric.status = "published"
    rubric.published_at = utcnow()
    audit(
        db,
        "rubric_published",
        actor_user_id=principal.user_id,
        entity_type="rubric_version",
        entity_id=rubric.id,
        detail={"version": rubric.version_label, "reevaluate": body.reevaluate},
    )
    await db.commit()
    return {
        "version": rubric.version_label,
        "status": "published",
        "publishedAt": iso(rubric.published_at),
    }


# ----------------------------------------------------------------- labeling
async def _ai_proposal(db: AsyncSession, case: LabelingCase) -> list[dict]:
    rows = (
        await db.execute(
            select(AreaScore.value, RubricArea.area_key)
            .join(RubricArea, AreaScore.rubric_area_id == RubricArea.id)
            .join(Report, AreaScore.report_id == Report.id)
            .where(Report.session_id == case.session_id, Report.is_current.is_(True))
            .order_by(RubricArea.sort_order)
        )
    ).all()
    return [{"area": key, "value": value} for value, key in rows]


@router.get("/master/labeling/queue")
async def labeling_queue(
    reason: str | None = Query(None),
    page: int = Query(1),
    pageSize: int = Query(20),
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if reason is not None and reason not in ("low_confidence", "borderline", "random"):
        raise AppError(
            400, "invalid_query", "Parámetros de filtro o paginación inválidos."
        )
    pagination: Pagination = pagination_params(page, pageSize)
    base = select(LabelingCase).where(LabelingCase.status == "pending")
    if reason:
        base = base.where(LabelingCase.reason == reason)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    cases = (
        await db.scalars(
            base.order_by(LabelingCase.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).all()
    items = []
    for case in cases:
        items.append(
            {
                "caseId": str(case.id),
                "sessionRef": str(case.session_id),
                "reason": case.reason,
                "aiProposal": await _ai_proposal(db, case),
            }
        )
    return {"items": items, "total": total}


async def _get_case(db: AsyncSession, case_id: str) -> LabelingCase:
    cid = to_uuid(case_id, "case_not_found")
    case = await db.get(LabelingCase, cid)
    if case is None:
        raise AppError(404, "case_not_found", "El caso no existe.")
    return case


@router.get("/master/labeling/cases/{case_id}")
async def labeling_case_detail(
    case_id: str,
    request: Request,
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    case = await _get_case(db, case_id)
    recording_url = None
    recording = await db.scalar(
        select(Recording)
        .where(Recording.session_id == case.session_id, Recording.status != "deleted")
        .order_by(Recording.created_at.desc())
        .limit(1)
    )
    if recording is not None:
        recording_url = get_storage().create_read_url(
            str(request.base_url), recording.blob_path
        )
    return {
        "caseId": str(case.id),
        "recordingUrl": recording_url,
        "aiProposal": await _ai_proposal(db, case),
        "reason": case.reason,
    }


@router.post("/master/labeling/cases/{case_id}/resolve")
async def resolve_labeling_case(
    case_id: str,
    body: ResolveCaseIn,
    principal: Principal = Depends(require_roles("master_config")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    case = await _get_case(db, case_id)
    if case.status == "resolved":
        raise AppError(409, "already_resolved", "El caso ya fue resuelto.")

    areas = list(
        (
            await db.scalars(
                select(RubricArea).where(
                    RubricArea.rubric_version_id == case.rubric_version_id
                )
            )
        ).all()
    )
    by_key = {area.area_key: area for area in areas}
    proposal = {p["area"]: p["value"] for p in await _ai_proposal(db, case)}

    for score in body.scores:
        if score.area not in by_key or not (0 <= score.value <= 100):
            raise AppError(
                400,
                "invalid_scores",
                "Área desconocida o valor fuera de 0-100.",
            )
    for score in body.scores:
        db.add(
            LabelingCorrection(
                labeling_case_id=case.id,
                rubric_area_id=by_key[score.area].id,
                ai_value=proposal.get(score.area, 0),
                corrected_value=score.value,
                comment=body.comment,
                corrected_by=principal.user_id,
            )
        )
    case.status = "resolved"
    case.resolved_by = principal.user_id
    case.resolved_at = utcnow()
    await db.commit()
    return {
        "caseId": str(case.id),
        "status": "resolved",
        "resolvedAt": iso(case.resolved_at),
    }
