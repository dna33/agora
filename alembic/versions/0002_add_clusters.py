"""add clustering tables

Revision ID: 0002_add_clusters
Revises: 0001_init_mvp
Create Date: 2026-02-20 00:30:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_clusters"
down_revision = "0001_init_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_clusters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("centroid_embedding", sa.JSON(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "message_cluster_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("cluster_id", sa.String(length=36), sa.ForeignKey("analysis_clusters.id"), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "cluster_id", name="uq_message_cluster"),
    )
    op.create_index("ix_message_cluster_assignments_message_id", "message_cluster_assignments", ["message_id"])
    op.create_index("ix_message_cluster_assignments_cluster_id", "message_cluster_assignments", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_message_cluster_assignments_cluster_id", table_name="message_cluster_assignments")
    op.drop_index("ix_message_cluster_assignments_message_id", table_name="message_cluster_assignments")
    op.drop_table("message_cluster_assignments")
    op.drop_table("analysis_clusters")
