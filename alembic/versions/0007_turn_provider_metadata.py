"""add provider metadata to thread messages

Revision ID: 0007_turn_meta
Revises: 0006_thread_context
Create Date: 2026-02-28 00:40:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0007_turn_meta"
down_revision = "0006_thread_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("thread_messages", sa.Column("provider_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("thread_messages", "provider_metadata")
