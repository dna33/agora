from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Message, TaxonomyCandidate
from app.schemas.taxonomy import (
    TaxonomyCandidateDecisionResponse,
    TaxonomyCandidateListResponse,
    TaxonomyCandidateResponse,
)

VALID_TAXONOMY_TYPES = {"primary_topic", "desired_future", "tension_type"}


def _normalize_label(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def maybe_record_taxonomy_candidate(db: Session, message: Message, extraction_raw: dict) -> None:
    if not isinstance(extraction_raw, dict):
        return

    fit_raw = extraction_raw.get("taxonomy_fit_score")
    gap_type = str(extraction_raw.get("taxonomy_gap_type") or "none")
    candidate_label = str(extraction_raw.get("taxonomy_candidate_label") or "").strip()
    reason = str(extraction_raw.get("taxonomy_candidate_reason") or "").strip() or None

    try:
        fit_score = float(fit_raw) if fit_raw is not None else 1.0
    except (TypeError, ValueError):
        fit_score = 1.0

    if fit_score >= 0.55:
        return
    if gap_type not in VALID_TAXONOMY_TYPES:
        return
    if not candidate_label:
        return

    normalized = _normalize_label(candidate_label)
    if not normalized:
        return

    existing = db.execute(
        select(TaxonomyCandidate).where(
            TaxonomyCandidate.status == "pending",
            TaxonomyCandidate.place_id == message.place_id,
            TaxonomyCandidate.taxonomy_type == gap_type,
            TaxonomyCandidate.normalized_label == normalized,
        )
    ).scalar_one_or_none()

    if existing:
        existing.support_count += 1
        existing.fit_score = min(existing.fit_score, fit_score)
        existing.reason = reason or existing.reason
        existing.message_id = message.id
        return

    db.add(
        TaxonomyCandidate(
            place_id=message.place_id,
            message_id=message.id,
            taxonomy_type=gap_type,
            candidate_label=candidate_label[:128],
            normalized_label=normalized[:128],
            reason=(reason[:280] if reason else None),
            fit_score=max(0.0, min(1.0, fit_score)),
            support_count=1,
            status="pending",
        )
    )


def list_taxonomy_candidates(
    db: Session,
    status: str | None = "pending",
    limit: int = 100,
    offset: int = 0,
) -> TaxonomyCandidateListResponse:
    if limit < 1:
        limit = 100
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    query = select(TaxonomyCandidate)
    count_query = select(func.count(TaxonomyCandidate.id))
    if status and status != "all":
        query = query.where(TaxonomyCandidate.status == status)
        count_query = count_query.where(TaxonomyCandidate.status == status)

    total = db.execute(count_query).scalar_one() or 0
    rows = db.execute(
        query.order_by(TaxonomyCandidate.support_count.desc(), TaxonomyCandidate.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    items = [
        TaxonomyCandidateResponse(
            id=r.id,
            place_id=r.place_id,
            message_id=r.message_id,
            taxonomy_type=r.taxonomy_type,
            candidate_label=r.candidate_label,
            normalized_label=r.normalized_label,
            reason=r.reason,
            fit_score=r.fit_score,
            support_count=r.support_count,
            status=r.status,
            review_note=r.review_note,
            approved_at=r.approved_at,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return TaxonomyCandidateListResponse(total=int(total), limit=limit, offset=offset, items=items)


def decide_taxonomy_candidate(
    db: Session,
    candidate_id: str,
    status: str,
    review_note: str | None = None,
) -> TaxonomyCandidateDecisionResponse | None:
    row = db.execute(select(TaxonomyCandidate).where(TaxonomyCandidate.id == candidate_id)).scalar_one_or_none()
    if row is None:
        return None

    status_norm = status.lower().strip()
    if status_norm not in {"approved", "rejected"}:
        status_norm = "rejected"

    row.status = status_norm
    row.review_note = (review_note or "").strip()[:280] or None
    row.approved_at = datetime.now(timezone.utc) if status_norm == "approved" else None

    db.flush()
    return TaxonomyCandidateDecisionResponse(
        id=row.id,
        status=row.status,
        review_note=row.review_note,
        approved_at=row.approved_at,
    )
