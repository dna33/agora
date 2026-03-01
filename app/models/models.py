import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CorridorSegment(Base):
    __tablename__ = "corridor_segments"
    __table_args__ = (UniqueConstraint("place_id", "name", name="uq_corridor_segment_place_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    order_index: Mapped[int] = mapped_column(Integer, index=True)
    min_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    place: Mapped["Place | None"] = relationship(back_populates="segments")


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    wa_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    context_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    segments: Mapped[list[CorridorSegment]] = relationship(back_populates="place")
    messages: Mapped[list["Message"]] = relationship(back_populates="place")
    threads: Mapped[list["ConversationThread"]] = relationship(back_populates="place")
    entries: Mapped[list["ConversationEntry"]] = relationship(back_populates="place")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[str] = mapped_column(String(16))
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    place_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    presence_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"), nullable=True, index=True)
    corridor_segment_id: Mapped[int | None] = mapped_column(ForeignKey("corridor_segments.id"), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    place: Mapped[Place | None] = relationship(back_populates="messages")
    analyses: Mapped[list["AnalysisVersion"]] = relationship(back_populates="message", cascade="all,delete")
    cluster_assignments: Mapped[list["MessageClusterAssignment"]] = relationship(
        back_populates="message", cascade="all,delete"
    )


class AnalysisVersion(Base):
    __tablename__ = "analysis_versions"
    __table_args__ = (UniqueConstraint("message_id", "version", name="uq_message_analysis_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    summary_line: Mapped[str] = mapped_column(String(280))
    primary_topic: Mapped[str] = mapped_column(String(64))
    desired_future: Mapped[str] = mapped_column(String(64))
    tension_type: Mapped[str] = mapped_column(String(64))
    quote_snippet: Mapped[str] = mapped_column(String(280))
    extraction_json: Mapped[dict] = mapped_column(JSON)
    clarification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped[Message] = relationship(back_populates="analyses")


class FeedbackToken(Base):
    __tablename__ = "feedback_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    allow_public_quote: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpenAICallLog(Base):
    __tablename__ = "openai_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    call_type: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_cost_input: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_cost_output: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_cost_audio_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pricing_version: Mapped[str] = mapped_column(String(32))
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisCluster(Base):
    __tablename__ = "analysis_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    label: Mapped[str] = mapped_column(String(128))
    centroid_embedding: Mapped[list[float]] = mapped_column(JSON)
    size: Mapped[int] = mapped_column(Integer, default=0)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assignments: Mapped[list["MessageClusterAssignment"]] = relationship(
        back_populates="cluster", cascade="all,delete"
    )


class MessageClusterAssignment(Base):
    __tablename__ = "message_cluster_assignments"
    __table_args__ = (UniqueConstraint("message_id", "cluster_id", name="uq_message_cluster"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("analysis_clusters.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped[Message] = relationship(back_populates="cluster_assignments")
    cluster: Mapped[AnalysisCluster] = relationship(back_populates="assignments")


class ConversationThread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp")
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(16), default="NEW", index=True)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    max_turns: Mapped[int] = mapped_column(Integer, default=3)
    initial_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_theme: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_zone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    context_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_place_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    place: Mapped[Place] = relationship(back_populates="threads")
    turns: Mapped[list["ConversationTurn"]] = relationship(back_populates="thread", cascade="all,delete")
    entries: Mapped[list["ConversationEntry"]] = relationship(back_populates="thread", cascade="all,delete")


class ConversationTurn(Base):
    __tablename__ = "thread_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8), index=True)  # IN | OUT
    raw_text: Mapped[str] = mapped_column(Text)
    provider_msg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    thread: Mapped[ConversationThread] = relationship(back_populates="turns")


class ConversationEntry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    initial_text: Mapped[str] = mapped_column(Text)
    refined_text: Mapped[str] = mapped_column(Text)
    labels: Mapped[dict] = mapped_column(JSON)
    corpus_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    thread: Mapped[ConversationThread] = relationship(back_populates="entries")
    place: Mapped[Place] = relationship(back_populates="entries")


class TaxonomyCandidate(Base):
    __tablename__ = "taxonomy_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    taxonomy_type: Mapped[str] = mapped_column(String(32), index=True)  # primary_topic | desired_future | tension_type
    candidate_label: Mapped[str] = mapped_column(String(128))
    normalized_label: Mapped[str] = mapped_column(String(128), index=True)
    reason: Mapped[str | None] = mapped_column(String(280), nullable=True)
    fit_score: Mapped[float] = mapped_column(Float, default=1.0, index=True)
    support_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
    review_note: Mapped[str | None] = mapped_column(String(280), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SentimentAuditReview(Base):
    __tablename__ = "sentiment_audit_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reviewer_tag: Mapped[str] = mapped_column(String(64), index=True)
    compared_count: Mapped[int] = mapped_column(Integer, default=0)
    model_matches: Mapped[int] = mapped_column(Integer, default=0)
    heuristic_matches: Mapped[int] = mapped_column(Integer, default=0)
    model_accuracy_pct: Mapped[float] = mapped_column(Float, default=0.0)
    heuristic_accuracy_pct: Mapped[float] = mapped_column(Float, default=0.0)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
