from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_plain_token, token_expiry, token_hash
from app.models import AnalysisVersion, FeedbackToken, Message, OpenAICallLog
from app.schemas.ingest import IngestRequest, IngestResponse
from app.services.corridor import assign_corridor_segment
from app.services.model_service import ModelService
from app.services.place_service import get_or_create_place
from app.services.taxonomy_service import maybe_record_taxonomy_candidate

settings = get_settings()


def ingest_message(db: Session, payload: IngestRequest) -> IngestResponse:
    model_service = ModelService()

    source_type = "audio" if payload.audio_base64 else "text"
    transcript_text = payload.text
    if payload.audio_base64:
        transcript_text = model_service.transcribe(db, payload.audio_base64, payload.audio_seconds)

    place = get_or_create_place(
        db,
        code=payload.place_code or settings.default_place_code,
        default_name=settings.default_place_name,
        city=settings.default_place_city,
        country=settings.default_place_country,
    )
    segment_id = assign_corridor_segment(db, payload.latitude, payload.longitude, place_id=place.id)

    message = Message(
        source_type=source_type,
        original_text=payload.text if source_type == "text" else None,
        transcript_text=transcript_text,
        place_reference=payload.place_reference,
        latitude=payload.latitude,
        longitude=payload.longitude,
        presence_mode=payload.presence_mode,
        place_id=place.id,
        corridor_segment_id=segment_id,
    )
    db.add(message)
    db.flush()

    extraction = model_service.extract(db, transcript_text or "", message.id)
    embedding = model_service.embed(db, transcript_text or "", message.id)
    message.embedding = embedding

    analysis = AnalysisVersion(
        message_id=message.id,
        version=1,
        summary_line=extraction.summary_line,
        primary_topic=extraction.primary_topic,
        desired_future=extraction.desired_future,
        tension_type=extraction.tension_type,
        quote_snippet=extraction.quote_snippet,
        extraction_json=extraction.raw,
        created_by="system",
    )
    db.add(analysis)
    maybe_record_taxonomy_candidate(db, message=message, extraction_raw=extraction.raw)

    plain_token = generate_plain_token()
    fb_token = FeedbackToken(
        message_id=message.id,
        token_hash=token_hash(plain_token),
        expires_at=token_expiry(settings.token_ttl_hours),
    )
    db.add(fb_token)

    db.commit()

    total_cost = (
        db.execute(
            select(func.coalesce(func.sum(OpenAICallLog.total_cost_usd), 0.0)).where(
                OpenAICallLog.message_id == message.id
            )
        ).scalar_one()
        or 0.0
    )

    return IngestResponse(
        message_id=str(message.id),
        analysis_version=1,
        feedback_link=f"{settings.public_base_url}/feedback/{plain_token}/edit",
        summary_line=analysis.summary_line,
        primary_topic=analysis.primary_topic,
        desired_future=analysis.desired_future,
        tension_type=analysis.tension_type,
        quote_snippet=analysis.quote_snippet,
        estimated_cost_usd=float(total_cost),
        corridor_segment_id=segment_id,
        source_type=source_type,
    )
