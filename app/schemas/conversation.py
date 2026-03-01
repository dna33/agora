from datetime import datetime

from pydantic import BaseModel


class ThreadResponse(BaseModel):
    id: str
    place_id: int
    channel: str
    user_id: str
    state: str
    turn_count: int
    max_turns: int
    created_at: datetime
    updated_at: datetime


class EntryResponse(BaseModel):
    id: str
    thread_id: str
    place_id: int
    user_id: str
    initial_text: str
    refined_text: str
    labels: dict
    corpus_message_id: str | None
    created_at: datetime


class ThreadTurnResponse(BaseModel):
    id: str
    thread_id: str
    direction: str
    raw_text: str
    provider_msg_id: str | None
    provider_metadata: dict | None
    timestamp: datetime
