from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import token_hash
from app.models import AnalysisVersion, FeedbackToken, Message
from app.schemas.feedback import FeedbackPatchRequest, FeedbackPatchResponse, FeedbackViewResponse


def _resolve_token(db: Session, plain_token: str) -> FeedbackToken:
    token = db.execute(select(FeedbackToken).where(FeedbackToken.token_hash == token_hash(plain_token))).scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Feedback token not found")
    if token.revoked:
        raise HTTPException(status_code=403, detail="Feedback token revoked")
    expires_at = token.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Feedback token expired")
    return token


def get_feedback_view(db: Session, plain_token: str) -> FeedbackViewResponse:
    token = _resolve_token(db, plain_token)
    message = db.get(Message, token.message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    latest = db.execute(
        select(AnalysisVersion)
        .where(AnalysisVersion.message_id == message.id)
        .order_by(AnalysisVersion.version.desc())
        .limit(1)
    ).scalar_one()

    return FeedbackViewResponse(
        message_id=str(message.id),
        original_text=message.original_text,
        transcript_text=message.transcript_text,
        latest_version=latest.version,
        summary_line=latest.summary_line,
        primary_topic=latest.primary_topic,
        desired_future=latest.desired_future,
        tension_type=latest.tension_type,
        quote_snippet=latest.quote_snippet,
        allow_public_quote=token.allow_public_quote,
        clarification_note=latest.clarification_note,
        place_reference=message.place_reference,
    )


def patch_feedback(db: Session, plain_token: str, patch: FeedbackPatchRequest) -> FeedbackPatchResponse:
    token = _resolve_token(db, plain_token)
    message = db.get(Message, token.message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    latest = db.execute(
        select(AnalysisVersion)
        .where(AnalysisVersion.message_id == message.id)
        .order_by(AnalysisVersion.version.desc())
        .limit(1)
    ).scalar_one()

    new_version = AnalysisVersion(
        message_id=message.id,
        version=latest.version + 1,
        summary_line=patch.summary_line or latest.summary_line,
        primary_topic=patch.primary_topic or latest.primary_topic,
        desired_future=patch.desired_future or latest.desired_future,
        tension_type=patch.tension_type or latest.tension_type,
        quote_snippet=patch.quote_snippet or latest.quote_snippet,
        clarification_note=patch.clarification_note or latest.clarification_note,
        extraction_json={
            "base_version": latest.version,
            "summary_line": patch.summary_line or latest.summary_line,
            "primary_topic": patch.primary_topic or latest.primary_topic,
            "desired_future": patch.desired_future or latest.desired_future,
            "tension_type": patch.tension_type or latest.tension_type,
            "quote_snippet": patch.quote_snippet or latest.quote_snippet,
            "clarification_note": patch.clarification_note or latest.clarification_note,
        },
        created_by="user_correction",
    )
    db.add(new_version)

    if patch.allow_public_quote is not None:
        token.allow_public_quote = patch.allow_public_quote
    if patch.place_reference is not None:
        message.place_reference = patch.place_reference

    db.commit()

    return FeedbackPatchResponse(
        message_id=str(message.id),
        new_version=new_version.version,
        summary_line=new_version.summary_line,
        primary_topic=new_version.primary_topic,
        desired_future=new_version.desired_future,
        tension_type=new_version.tension_type,
        quote_snippet=new_version.quote_snippet,
        allow_public_quote=token.allow_public_quote,
        place_reference=message.place_reference,
    )
