"""add context memory fields to threads

Revision ID: 0006_thread_context
Revises: 0005_conv_threads
Create Date: 2026-02-28 00:20:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0006_thread_context"
down_revision = "0005_conv_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("context_theme", sa.String(length=32), nullable=True))
    op.add_column("threads", sa.Column("context_zone", sa.String(length=128), nullable=True))
    op.add_column("threads", sa.Column("context_time", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("threads", "context_time")
    op.drop_column("threads", "context_zone")
    op.drop_column("threads", "context_theme")
