from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.taxonomies import PRESENCE_MODES


class IngestRequest(BaseModel):
    text: str | None = None
    audio_base64: str | None = None
    audio_seconds: float | None = None
    place_code: str | None = Field(default=None, max_length=64)
    place_reference: str | None = Field(default=None, max_length=256)
    latitude: float | None = None
    longitude: float | None = None
    presence_mode: str | None = None

    @field_validator("presence_mode")
    @classmethod
    def validate_presence(cls, value: str | None):
        if value is None:
            return value
        if value not in PRESENCE_MODES:
            raise ValueError(f"presence_mode must be one of: {', '.join(PRESENCE_MODES)}")
        return value

    @field_validator("audio_base64")
    @classmethod
    def check_input(cls, value: str | None, info):
        text = info.data.get("text")
        if not text and not value:
            raise ValueError("Either text or audio_base64 must be provided")
        return value


class IngestResponse(BaseModel):
    message_id: str
    analysis_version: int
    feedback_link: str
    summary_line: str
    primary_topic: str
    desired_future: str
    tension_type: str
    quote_snippet: str
    estimated_cost_usd: float
    corridor_segment_id: int | None
    source_type: Literal["text", "audio"]
