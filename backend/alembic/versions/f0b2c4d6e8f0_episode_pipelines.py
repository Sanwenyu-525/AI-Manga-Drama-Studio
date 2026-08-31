"""episode_pipelines: C2 一键成片流水线（mvp-spec DOC-C2）

One episode's end-to-end production run: analyze(preview) → human confirm →
shots → images → timeline → render. The row is the durable source of truth for
断点续跑 (resume re-runs from the first non-done stage).

Revision ID: f0b2c4d6e8f0
Revises: e4f6a8c0d2e4
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0b2c4d6e8f0"
down_revision: Union[str, Sequence[str], None] = "e4f6a8c0d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "episode_pipelines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column("stages_json", sa.Text(), nullable=False),
        sa.Column("snapshot_id", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_episode_pipelines_episode_id", "episode_pipelines", ["episode_id"])
    op.create_index("ix_episode_pipelines_project_id", "episode_pipelines", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_episode_pipelines_project_id", table_name="episode_pipelines")
    op.drop_index("ix_episode_pipelines_episode_id", table_name="episode_pipelines")
    op.drop_table("episode_pipelines")
