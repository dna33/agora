"""add conversation threads and entries

Revision ID: 0005_conv_threads
Revises: 0004_segment_unique_per_place
Create Date: 2026-02-28 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0005_conv_threads"
down_revision = "0004_segment_unique_per_place"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("places", sa.Column("wa_number", sa.String(length=64), nullable=True))
    op.add_column("places", sa.Column("context_prompt", sa.Text(), nullable=True))
    op.add_column("places", sa.Column("settings", sa.JSON(), nullable=True))
    op.create_index("ix_places_wa_number", "places", ["wa_number"])

    op.create_table(
        "threads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id"), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("max_turns", sa.Integer(), nullable=False),
        sa.Column("initial_text", sa.Text(), nullable=True),
        sa.Column("last_intent", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_threads_place_id", "threads", ["place_id"])
    op.create_index("ix_threads_user_id", "threads", ["user_id"])
    op.create_index("ix_threads_state", "threads", ["state"])

    op.create_table(
        "thread_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), sa.ForeignKey("threads.id"), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("provider_msg_id", sa.String(length=128), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_thread_messages_thread_id", "thread_messages", ["thread_id"])
    op.create_index("ix_thread_messages_direction", "thread_messages", ["direction"])
    op.create_index("ix_thread_messages_timestamp", "thread_messages", ["timestamp"])

    op.create_table(
        "entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("thread_id", sa.String(length=36), sa.ForeignKey("threads.id"), nullable=False),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("places.id"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("initial_text", sa.Text(), nullable=False),
        sa.Column("refined_text", sa.Text(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("corpus_message_id", sa.String(length=36), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_entries_thread_id", "entries", ["thread_id"])
    op.create_index("ix_entries_place_id", "entries", ["place_id"])
    op.create_index("ix_entries_user_id", "entries", ["user_id"])
    op.create_index("ix_entries_corpus_message_id", "entries", ["corpus_message_id"])


def downgrade() -> None:
    op.drop_index("ix_entries_corpus_message_id", table_name="entries")
    op.drop_index("ix_entries_user_id", table_name="entries")
    op.drop_index("ix_entries_place_id", table_name="entries")
    op.drop_index("ix_entries_thread_id", table_name="entries")
    op.drop_table("entries")

    op.drop_index("ix_thread_messages_timestamp", table_name="thread_messages")
    op.drop_index("ix_thread_messages_direction", table_name="thread_messages")
    op.drop_index("ix_thread_messages_thread_id", table_name="thread_messages")
    op.drop_table("thread_messages")

    op.drop_index("ix_threads_state", table_name="threads")
    op.drop_index("ix_threads_user_id", table_name="threads")
    op.drop_index("ix_threads_place_id", table_name="threads")
    op.drop_table("threads")

    op.drop_index("ix_places_wa_number", table_name="places")
    op.drop_column("places", "settings")
    op.drop_column("places", "context_prompt")
    op.drop_column("places", "wa_number")
