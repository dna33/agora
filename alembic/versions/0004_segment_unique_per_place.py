"""segment unique per place

Revision ID: 0004_segment_unique_per_place
Revises: 0003_add_places
Create Date: 2026-02-21 00:20:00

"""

from alembic import op


revision = "0004_segment_unique_per_place"
down_revision = "0003_add_places"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE corridor_segments DROP CONSTRAINT IF EXISTS corridor_segments_name_key")
    op.create_unique_constraint(
        "uq_corridor_segment_place_name",
        "corridor_segments",
        ["place_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_corridor_segment_place_name", "corridor_segments", type_="unique")
    op.create_unique_constraint("corridor_segments_name_key", "corridor_segments", ["name"])
