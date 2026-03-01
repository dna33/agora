"""add taxonomy candidates table

Revision ID: 0009_taxonomy_candidates
Revises: 0008_thread_geo
Create Date: 2026-02-28 13:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0009_taxonomy_candidates"
down_revision = "0008_thread_geo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "taxonomy_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("taxonomy_type", sa.String(length=32), nullable=False),
        sa.Column("candidate_label", sa.String(length=128), nullable=False),
        sa.Column("normalized_label", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=280), nullable=True),
        sa.Column("fit_score", sa.Float(), nullable=False),
        sa.Column("support_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("review_note", sa.String(length=280), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_taxonomy_candidates_place_id", "taxonomy_candidates", ["place_id"])
    op.create_index("ix_taxonomy_candidates_message_id", "taxonomy_candidates", ["message_id"])
    op.create_index("ix_taxonomy_candidates_taxonomy_type", "taxonomy_candidates", ["taxonomy_type"])
    op.create_index("ix_taxonomy_candidates_normalized_label", "taxonomy_candidates", ["normalized_label"])
    op.create_index("ix_taxonomy_candidates_fit_score", "taxonomy_candidates", ["fit_score"])
    op.create_index("ix_taxonomy_candidates_status", "taxonomy_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_taxonomy_candidates_status", table_name="taxonomy_candidates")
    op.drop_index("ix_taxonomy_candidates_fit_score", table_name="taxonomy_candidates")
    op.drop_index("ix_taxonomy_candidates_normalized_label", table_name="taxonomy_candidates")
    op.drop_index("ix_taxonomy_candidates_taxonomy_type", table_name="taxonomy_candidates")
    op.drop_index("ix_taxonomy_candidates_message_id", table_name="taxonomy_candidates")
    op.drop_index("ix_taxonomy_candidates_place_id", table_name="taxonomy_candidates")
    op.drop_table("taxonomy_candidates")
