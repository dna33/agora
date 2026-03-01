from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import AnalysisVersion, Message
from app.schemas.sentiment_audit import (
    SentimentAuditEvaluateRequest,
    SentimentAuditEvaluateResponse,
    SentimentAuditSampleItem,
    SentimentAuditSampleResponse,
)


def _heuristic_label(text: str) -> str:
    norm = (text or "").lower()
    positive_terms = [
        "me gusta",
        "bonito",
        "tranquilo",
        "limpio",
        "agradable",
        "mejor",
        "verde",
        "seguro",
    ]
    negative_terms = [
        "miedo",
        "insegur",
        "basura",
        "sucio",
        "ruido",
        "peligro",
        "oscuro",
        "robo",
        "falta",
        "horrible",
        "pesimo",
    ]
    pos = sum(1 for t in positive_terms if t in norm)
    neg = sum(1 for t in negative_terms if t in norm)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _label_from_score(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score <= -0.2:
        return "negative"
    if score >= 0.2:
        return "positive"
    return "neutral"


def _sample_rows(db: Session, sample_size: int):
    latest_version = (
        select(
            AnalysisVersion.message_id.label("message_id"),
            func.max(AnalysisVersion.version).label("max_version"),
        )
        .group_by(AnalysisVersion.message_id)
        .subquery()
    )

    q = (
        select(
            Message.id,
            Message.original_text,
            Message.transcript_text,
            AnalysisVersion.extraction_json,
        )
        .outerjoin(latest_version, latest_version.c.message_id == Message.id)
        .outerjoin(
            AnalysisVersion,
            and_(
                AnalysisVersion.message_id == Message.id,
                AnalysisVersion.version == latest_version.c.max_version,
            ),
        )
        .order_by(func.random())
        .limit(sample_size)
    )
    return db.execute(q).all()


def get_sentiment_audit_sample(db: Session, sample_size: int = 10) -> SentimentAuditSampleResponse:
    n = max(1, min(100, int(sample_size)))
    rows = _sample_rows(db, n)
    items: list[SentimentAuditSampleItem] = []
    for row in rows:
        text = row.transcript_text or row.original_text or ""
        model_label = "neutral"
        model_score = None
        if isinstance(row.extraction_json, dict):
            raw_label = row.extraction_json.get("sentiment_label")
            raw_score = row.extraction_json.get("sentiment_score")
            if isinstance(raw_label, str) and raw_label.lower() in {"negative", "neutral", "positive"}:
                model_label = raw_label.lower()
            try:
                if raw_score is not None:
                    model_score = float(raw_score)
            except (TypeError, ValueError):
                model_score = None
            if model_score is not None and not isinstance(raw_label, str):
                model_label = _label_from_score(model_score)

        items.append(
            SentimentAuditSampleItem(
                message_id=row.id,
                text=text[:500],
                model_label=model_label,
                model_score=model_score,
                heuristic_label=_heuristic_label(text),
            )
        )
    return SentimentAuditSampleResponse(sample_size=len(items), items=items)


def evaluate_sentiment_audit(db: Session, payload: SentimentAuditEvaluateRequest) -> SentimentAuditEvaluateResponse:
    if not payload.items:
        return SentimentAuditEvaluateResponse(
            compared_count=0,
            model_matches=0,
            heuristic_matches=0,
            model_accuracy_pct=0.0,
            heuristic_accuracy_pct=0.0,
        )

    by_id = {item.message_id: item.manual_label for item in payload.items}
    # Compare exactly the ids selected by admin in the UI.
    latest_version = (
        select(
            AnalysisVersion.message_id.label("message_id"),
            func.max(AnalysisVersion.version).label("max_version"),
        )
        .group_by(AnalysisVersion.message_id)
        .subquery()
    )
    rows = db.execute(
        select(Message.id, Message.original_text, Message.transcript_text, AnalysisVersion.extraction_json)
        .outerjoin(latest_version, latest_version.c.message_id == Message.id)
        .outerjoin(
            AnalysisVersion,
            and_(
                AnalysisVersion.message_id == Message.id,
                AnalysisVersion.version == latest_version.c.max_version,
            ),
        )
        .where(Message.id.in_(list(by_id.keys())))
    ).all()

    compared = 0
    model_matches = 0
    heuristic_matches = 0
    for row in rows:
        manual = by_id.get(row.id)
        if manual is None:
            continue
        compared += 1
        text = row.transcript_text or row.original_text or ""
        heuristic = _heuristic_label(text)
        model_label = "neutral"
        if isinstance(row.extraction_json, dict):
            raw_label = row.extraction_json.get("sentiment_label")
            raw_score = row.extraction_json.get("sentiment_score")
            if isinstance(raw_label, str) and raw_label.lower() in {"negative", "neutral", "positive"}:
                model_label = raw_label.lower()
            else:
                try:
                    score = float(raw_score) if raw_score is not None else None
                except (TypeError, ValueError):
                    score = None
                model_label = _label_from_score(score)

        if model_label == manual:
            model_matches += 1
        if heuristic == manual:
            heuristic_matches += 1

    if compared == 0:
        return SentimentAuditEvaluateResponse(
            compared_count=0,
            model_matches=0,
            heuristic_matches=0,
            model_accuracy_pct=0.0,
            heuristic_accuracy_pct=0.0,
        )

    return SentimentAuditEvaluateResponse(
        compared_count=compared,
        model_matches=model_matches,
        heuristic_matches=heuristic_matches,
        model_accuracy_pct=round((model_matches / compared) * 100, 2),
        heuristic_accuracy_pct=round((heuristic_matches / compared) * 100, 2),
    )
