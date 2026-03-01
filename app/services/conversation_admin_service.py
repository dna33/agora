from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConversationEntry, ConversationThread, ConversationTurn
from app.schemas.conversation import EntryResponse, ThreadResponse, ThreadTurnResponse


def list_place_entries(db: Session, place_id: int, limit: int = 100, offset: int = 0) -> list[EntryResponse]:
    entries = db.execute(
        select(ConversationEntry)
        .where(ConversationEntry.place_id == place_id)
        .order_by(ConversationEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return [
        EntryResponse(
            id=e.id,
            thread_id=e.thread_id,
            place_id=e.place_id,
            user_id=e.user_id,
            initial_text=e.initial_text,
            refined_text=e.refined_text,
            labels=e.labels,
            corpus_message_id=e.corpus_message_id,
            created_at=e.created_at,
        )
        for e in entries
    ]


def list_place_threads(db: Session, place_id: int, limit: int = 100, offset: int = 0) -> list[ThreadResponse]:
    threads = db.execute(
        select(ConversationThread)
        .where(ConversationThread.place_id == place_id)
        .order_by(ConversationThread.updated_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return [
        ThreadResponse(
            id=t.id,
            place_id=t.place_id,
            channel=t.channel,
            user_id=t.user_id,
            state=t.state,
            turn_count=t.turn_count,
            max_turns=t.max_turns,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in threads
    ]


def list_thread_turns(
    db: Session,
    place_id: int,
    thread_id: str,
    limit: int = 200,
    offset: int = 0,
) -> list[ThreadTurnResponse]:
    thread = db.execute(
        select(ConversationThread).where(ConversationThread.id == thread_id, ConversationThread.place_id == place_id)
    ).scalar_one_or_none()
    if thread is None:
        return []

    turns = db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.thread_id == thread_id)
        .order_by(ConversationTurn.timestamp.asc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return [
        ThreadTurnResponse(
            id=t.id,
            thread_id=t.thread_id,
            direction=t.direction,
            raw_text=t.raw_text,
            provider_msg_id=t.provider_msg_id,
            provider_metadata=t.provider_metadata,
            timestamp=t.timestamp,
        )
        for t in turns
    ]
