"""add places abstraction

Revision ID: 0003_add_places
Revises: 0002_add_clusters
Create Date: 2026-02-21 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_places"
down_revision = "0002_add_clusters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_places_code", "places", ["code"])

    op.add_column("messages", sa.Column("place_id", sa.Integer(), nullable=True))
    op.create_index("ix_messages_place_id", "messages", ["place_id"])
    op.create_foreign_key("fk_messages_place_id", "messages", "places", ["place_id"], ["id"])

    op.add_column("corridor_segments", sa.Column("place_id", sa.Integer(), nullable=True))
    op.create_index("ix_corridor_segments_place_id", "corridor_segments", ["place_id"])
    op.create_foreign_key(
        "fk_corridor_segments_place_id",
        "corridor_segments",
        "places",
        ["place_id"],
        ["id"],
    )

    op.execute(
        """
        INSERT INTO places (code, name, city, country, created_at)
        VALUES ('alameda-santiago', 'Alameda Santiago', 'Santiago', 'Chile', CURRENT_TIMESTAMP)
        """
    )
    op.execute(
        """
        UPDATE corridor_segments
        SET place_id = (SELECT id FROM places WHERE code = 'alameda-santiago')
        WHERE place_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_corridor_segments_place_id", "corridor_segments", type_="foreignkey")
    op.drop_index("ix_corridor_segments_place_id", table_name="corridor_segments")
    op.drop_column("corridor_segments", "place_id")

    op.drop_constraint("fk_messages_place_id", "messages", type_="foreignkey")
    op.drop_index("ix_messages_place_id", table_name="messages")
    op.drop_column("messages", "place_id")

    op.drop_index("ix_places_code", table_name="places")
    op.drop_table("places")
