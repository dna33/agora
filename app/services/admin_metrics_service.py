import csv
import io
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.taxonomies import PRIMARY_TOPIC_LABELS_ES
from app.models import (
    AnalysisVersion,
    ConversationEntry,
    ConversationThread,
    ConversationTurn,
    Message,
    OpenAICallLog,
)
from app.schemas.admin_metrics import (
    ConversationMetricsResponse,
    PipelineMetricsResponse,
    ReviewMessageItem,
    ReviewMessageListResponse,
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_pipeline_metrics(db: Session, period_days: int = 7) -> PipelineMetricsResponse:
    if period_days < 1:
        period_days = 7

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=period_days)
    day_ago = now - timedelta(hours=24)

    total_messages = db.execute(
        select(func.count(Message.id)).where(Message.created_at >= since)
    ).scalar_one() or 0

    messages_last_24h = db.execute(
        select(func.count(Message.id)).where(Message.created_at >= day_ago)
    ).scalar_one() or 0

    audio_messages = db.execute(
        select(func.count(Message.id)).where(Message.created_at >= since, Message.source_type == "audio")
    ).scalar_one() or 0

    corrected_messages = db.execute(
        select(func.count(func.distinct(AnalysisVersion.message_id))).where(
            AnalysisVersion.created_at >= since,
            AnalysisVersion.version > 1,
        )
    ).scalar_one() or 0

    total_cost = db.execute(
        select(func.coalesce(func.sum(OpenAICallLog.total_cost_usd), 0.0)).where(OpenAICallLog.created_at >= since)
    ).scalar_one() or 0.0

    rows = db.execute(
        select(Message.created_at, AnalysisVersion.created_at)
        .join(AnalysisVersion, AnalysisVersion.message_id == Message.id)
        .where(Message.created_at >= since, AnalysisVersion.version == 1)
    ).all()

    latencies = [(_as_utc(a_created) - _as_utc(m_created)).total_seconds() for m_created, a_created in rows]
    avg_latency = float(sum(latencies) / len(latencies)) if latencies else 0.0

    audio_share = (audio_messages / total_messages * 100) if total_messages else 0.0
    correction_rate = (corrected_messages / total_messages * 100) if total_messages else 0.0
    avg_cost = (total_cost / total_messages) if total_messages else 0.0

    return PipelineMetricsResponse(
        period_days=period_days,
        total_messages=int(total_messages),
        messages_last_24h=int(messages_last_24h),
        audio_share_pct=round(audio_share, 2),
        correction_rate_pct=round(correction_rate, 2),
        total_openai_cost_usd=round(float(total_cost), 6),
        avg_cost_per_message_usd=round(float(avg_cost), 6),
        avg_v1_latency_seconds=round(avg_latency, 2),
    )


def get_review_messages(db: Session, limit: int = 50, offset: int = 0) -> ReviewMessageListResponse:
    if limit < 1:
        limit = 50
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    total = db.execute(select(func.count(Message.id))).scalar_one() or 0

    messages = db.execute(
        select(Message)
        .options(joinedload(Message.analyses), joinedload(Message.place))
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).unique().scalars().all()

    items: list[ReviewMessageItem] = []
    for message in messages:
        analyses = sorted(message.analyses, key=lambda a: a.version)
        if analyses:
            v1 = analyses[0]
            final = analyses[-1]
            versions_count = len(analyses)
        else:
            v1 = None
            final = None
            versions_count = 0

        v1_topic = PRIMARY_TOPIC_LABELS_ES.get(v1.primary_topic, v1.primary_topic) if v1 else None
        final_topic = PRIMARY_TOPIC_LABELS_ES.get(final.primary_topic, final.primary_topic) if final else None

        items.append(
            ReviewMessageItem(
                message_id=message.id,
                created_at=_as_utc(message.created_at),
                place_code=message.place.code if message.place else None,
                latitude=message.latitude,
                longitude=message.longitude,
                source_type=message.source_type,
                original_text=message.original_text,
                transcript_text=message.transcript_text,
                v1_summary_line=v1.summary_line if v1 else None,
                v1_primary_topic=v1_topic,
                final_summary_line=final.summary_line if final else None,
                final_primary_topic=final_topic,
                versions_count=versions_count,
                corrected=versions_count > 1,
            )
        )

    return ReviewMessageListResponse(total=int(total), limit=limit, offset=offset, items=items)


def review_messages_to_csv(data: ReviewMessageListResponse) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "message_id",
            "created_at",
            "place_code",
            "latitude",
            "longitude",
            "source_type",
            "original_text",
            "transcript_text",
            "v1_summary_line",
            "v1_primary_topic",
            "final_summary_line",
            "final_primary_topic",
            "versions_count",
            "corrected",
        ]
    )

    for item in data.items:
        writer.writerow(
            [
                item.message_id,
                item.created_at.isoformat(),
                item.place_code or "",
                item.latitude if item.latitude is not None else "",
                item.longitude if item.longitude is not None else "",
                item.source_type,
                item.original_text or "",
                item.transcript_text or "",
                item.v1_summary_line or "",
                item.v1_primary_topic or "",
                item.final_summary_line or "",
                item.final_primary_topic or "",
                item.versions_count,
                str(item.corrected).lower(),
            ]
        )

    return output.getvalue()


def get_conversation_metrics(db: Session, period_days: int = 7) -> ConversationMetricsResponse:
    if period_days < 1:
        period_days = 7

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=period_days)

    threads_total = db.execute(
        select(func.count(ConversationThread.id)).where(ConversationThread.created_at >= since)
    ).scalar_one() or 0

    threads_collecting = db.execute(
        select(func.count(ConversationThread.id)).where(
            ConversationThread.created_at >= since,
            ConversationThread.state == "COLLECTING",
        )
    ).scalar_one() or 0

    threads_closed = db.execute(
        select(func.count(ConversationThread.id)).where(
            ConversationThread.created_at >= since,
            ConversationThread.state == "CLOSED",
        )
    ).scalar_one() or 0

    entries_total = db.execute(
        select(func.count(ConversationEntry.id)).where(ConversationEntry.created_at >= since)
    ).scalar_one() or 0

    avg_turn_count = db.execute(
        select(func.avg(ConversationThread.turn_count)).where(ConversationThread.created_at >= since)
    ).scalar_one()
    avg_turn_count = float(avg_turn_count or 0.0)

    in_turn_counts = db.execute(
        select(ConversationTurn.thread_id, func.count(ConversationTurn.id))
        .join(ConversationThread, ConversationThread.id == ConversationTurn.thread_id)
        .where(
            ConversationThread.created_at >= since,
            ConversationTurn.direction == "IN",
        )
        .group_by(ConversationTurn.thread_id)
    ).all()
    eligible = len(in_turn_counts)
    second_turn_threads = sum(1 for _, c in in_turn_counts if (c or 0) >= 2)

    close_rate = (threads_closed / threads_total * 100) if threads_total else 0.0
    second_turn_rate = (second_turn_threads / eligible * 100) if eligible else 0.0

    return ConversationMetricsResponse(
        period_days=period_days,
        threads_total=int(threads_total),
        threads_collecting=int(threads_collecting),
        threads_closed=int(threads_closed),
        close_rate_pct=round(close_rate, 2),
        entries_total=int(entries_total),
        second_turn_response_rate_pct=round(second_turn_rate, 2),
        avg_turn_count=round(avg_turn_count, 2),
    )
