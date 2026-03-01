"""add geo context fields to threads

Revision ID: 0008_thread_geo
Revises: 0007_turn_meta
Create Date: 2026-02-28 01:05:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0008_thread_geo"
down_revision = "0007_turn_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("context_latitude", sa.Float(), nullable=True))
    op.add_column("threads", sa.Column("context_longitude", sa.Float(), nullable=True))
    op.add_column("threads", sa.Column("context_place_reference", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("threads", "context_place_reference")
    op.drop_column("threads", "context_longitude")
    op.drop_column("threads", "context_latitude")
