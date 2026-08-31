"""P2-E1-T01: analysis_snapshots（不可变分析快照表）

Preview 落库快照，Confirm 只提交 snapshot（零 LLM 调用），从机制上消除
「确认写入的内容 ≠ 用户预览的内容」（真实 LLM 非确定性；Sprint 04 K1）。

Revision ID: b7c9d1e3f5a7
Revises: f3a5b7c9d1e3
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c9d1e3f5a7"
down_revision: Union[str, Sequence[str], None] = "f3a5b7c9d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("episode_id", sa.String(36), sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("episode_revision", sa.Integer(), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_scene_ids_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.Text(), nullable=True),
    )
    op.create_index("ix_analysis_snapshots_episode_id", "analysis_snapshots", ["episode_id"])
    op.create_index(
        "ix_analysis_snapshots_episode_status", "analysis_snapshots", ["episode_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_snapshots_episode_status", table_name="analysis_snapshots")
    op.drop_index("ix_analysis_snapshots_episode_id", table_name="analysis_snapshots")
    op.drop_table("analysis_snapshots")
