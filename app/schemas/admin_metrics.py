from datetime import datetime

from pydantic import BaseModel


class PipelineMetricsResponse(BaseModel):
    period_days: int
    total_messages: int
    messages_last_24h: int
    audio_share_pct: float
    correction_rate_pct: float
    total_openai_cost_usd: float
    avg_cost_per_message_usd: float
    avg_v1_latency_seconds: float


class ReviewMessageItem(BaseModel):
    message_id: str
    created_at: datetime
    place_code: str | None
    latitude: float | None
    longitude: float | None
    source_type: str
    original_text: str | None
    transcript_text: str | None
    v1_summary_line: str | None
    v1_primary_topic: str | None
    final_summary_line: str | None
    final_primary_topic: str | None
    versions_count: int
    corrected: bool


class ReviewMessageListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ReviewMessageItem]


class ConversationMetricsResponse(BaseModel):
    period_days: int
    threads_total: int
    threads_collecting: int
    threads_closed: int
    close_rate_pct: float
    entries_total: int
    second_turn_response_rate_pct: float
    avg_turn_count: float
