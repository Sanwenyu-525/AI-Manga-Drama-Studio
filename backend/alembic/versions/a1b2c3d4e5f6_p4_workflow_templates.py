"""P4-T004 (workflow_templates + workflow_versions)

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-08

Phase-4 first batch (mvp-spec / database-v0.1 §23-24):
- workflow_templates: read-only catalog registry (one row per workflow_id JSON template).
- workflow_versions: immutable SHA-256 hash snapshots of the template file (v1 on register).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("workflow_type", sa.Text(), nullable=False),
        sa.Column("workflow_id", sa.Text(), nullable=False),
        sa.Column("active_version_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("workflow_id", "workflow_type", name="uq_workflow_templates_workflow"),
    )
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["workflow_templates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("template_id", "version_number", name="uq_workflow_versions_template_version"),
    )
    op.create_index("idx_workflow_versions_template", "workflow_versions", ["template_id"])


def downgrade() -> None:
    op.drop_index("idx_workflow_versions_template", table_name="workflow_versions")
    op.drop_table("workflow_versions")
    op.drop_table("workflow_templates")
