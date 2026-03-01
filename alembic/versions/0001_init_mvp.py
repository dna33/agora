"""init mvp schema

Revision ID: 0001_init_mvp
Revises: 
Create Date: 2026-02-20 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init_mvp"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corridor_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("min_lat", sa.Float(), nullable=True),
        sa.Column("max_lat", sa.Float(), nullable=True),
        sa.Column("min_lon", sa.Float(), nullable=True),
        sa.Column("max_lon", sa.Float(), nullable=True),
    )
    op.create_index("ix_corridor_segments_order_index", "corridor_segments", ["order_index"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("place_reference", sa.String(length=256), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("presence_mode", sa.String(length=32), nullable=True),
        sa.Column("corridor_segment_id", sa.Integer(), sa.ForeignKey("corridor_segments.id"), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "analysis_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary_line", sa.String(length=280), nullable=False),
        sa.Column("primary_topic", sa.String(length=64), nullable=False),
        sa.Column("desired_future", sa.String(length=64), nullable=False),
        sa.Column("tension_type", sa.String(length=64), nullable=False),
        sa.Column("quote_snippet", sa.String(length=280), nullable=False),
        sa.Column("extraction_json", sa.JSON(), nullable=False),
        sa.Column("clarification_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "version", name="uq_message_analysis_version"),
    )
    op.create_index("ix_analysis_versions_message_id", "analysis_versions", ["message_id"])

    op.create_table(
        "feedback_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("allow_public_quote", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_tokens_message_id", "feedback_tokens", ["message_id"])
    op.create_index("ix_feedback_tokens_token_hash", "feedback_tokens", ["token_hash"])

    op.create_table(
        "openai_call_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("call_type", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("audio_seconds", sa.Float(), nullable=True),
        sa.Column("unit_cost_input", sa.Float(), nullable=True),
        sa.Column("unit_cost_output", sa.Float(), nullable=True),
        sa.Column("unit_cost_audio_second", sa.Float(), nullable=True),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("pricing_version", sa.String(length=32), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_openai_call_logs_message_id", "openai_call_logs", ["message_id"])
    op.create_index("ix_openai_call_logs_call_type", "openai_call_logs", ["call_type"])

    op.execute(
        """
        INSERT INTO corridor_segments (name, order_index, min_lat, max_lat, min_lon, max_lon)
        VALUES
          ('Torres Tajamar', 1, -33.4240, -33.4200, -70.6165, -70.6110),
          ('Baquedano-UC', 2, -33.4390, -33.4240, -70.6500, -70.6165),
          ('Santa Lucia-Moneda', 3, -33.4485, -33.4390, -70.6690, -70.6500),
          ('Moneda-Los Heroes', 4, -33.4565, -33.4485, -70.6795, -70.6690)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_openai_call_logs_call_type", table_name="openai_call_logs")
    op.drop_index("ix_openai_call_logs_message_id", table_name="openai_call_logs")
    op.drop_table("openai_call_logs")

    op.drop_index("ix_feedback_tokens_token_hash", table_name="feedback_tokens")
    op.drop_index("ix_feedback_tokens_message_id", table_name="feedback_tokens")
    op.drop_table("feedback_tokens")

    op.drop_index("ix_analysis_versions_message_id", table_name="analysis_versions")
    op.drop_table("analysis_versions")

    op.drop_table("messages")

    op.drop_index("ix_corridor_segments_order_index", table_name="corridor_segments")
    op.drop_table("corridor_segments")
