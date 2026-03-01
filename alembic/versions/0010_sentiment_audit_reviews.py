"""add sentiment audit reviews

Revision ID: 0010_sentiment_audit_reviews
Revises: 0009_taxonomy_candidates
Create Date: 2026-02-28 14:20:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0010_sentiment_audit_reviews"
down_revision = "0009_taxonomy_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sentiment_audit_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reviewer_tag", sa.String(length=64), nullable=False),
        sa.Column("compared_count", sa.Integer(), nullable=False),
        sa.Column("model_matches", sa.Integer(), nullable=False),
        sa.Column("heuristic_matches", sa.Integer(), nullable=False),
        sa.Column("model_accuracy_pct", sa.Float(), nullable=False),
        sa.Column("heuristic_accuracy_pct", sa.Float(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentiment_audit_reviews_reviewer_tag", "sentiment_audit_reviews", ["reviewer_tag"])


def downgrade() -> None:
    op.drop_index("ix_sentiment_audit_reviews_reviewer_tag", table_name="sentiment_audit_reviews")
    op.drop_table("sentiment_audit_reviews")
