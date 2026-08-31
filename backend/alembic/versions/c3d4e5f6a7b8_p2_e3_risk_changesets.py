"""P2-E3-T02/T03: proposal 风险元数据 + 过期 + agent_change_sets 表

- agent_proposals: risk_level/reason/estimated_tasks/estimated_cost/irreversible/
  expires_at（R0–R3 风险分级 + 审批过期失效语义）
- agent_change_sets: 每次 Agent mutation 的最小 before/after patch（可审阅、可撤销，
  Undo = 新补偿变更，不改历史）
- generations.run_id: agent 溯源（generate_image proposal approve 创建的生成任务
  携带 run_id，worker 完成回填 active 版本时据此记录 ChangeSet）

Revision ID: c3d4e5f6a7b8
Revises: b7c9d1e3f5a7
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b7c9d1e3f5a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # agent_proposals: risk metadata + expiry (P2-E3-T02)
    with op.batch_alter_table("agent_proposals") as batch:
        batch.add_column(sa.Column("risk_level", sa.Text(), nullable=True))
        batch.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("estimated_tasks", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_cost", sa.Float(), nullable=True))
        batch.add_column(sa.Column("irreversible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("expires_at", sa.Text(), nullable=True))

    # agent_change_sets (P2-E3-T03)
    op.create_table(
        "agent_change_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="agent"),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("revision_before", sa.Integer(), nullable=False),
        sa.Column("revision_after", sa.Integer(), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("undone", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("undone_at", sa.Text(), nullable=True),
        sa.Column("undone_by_change_set_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_agent_change_sets_project", "agent_change_sets", ["project_id"])
    op.create_index("ix_agent_change_sets_run", "agent_change_sets", ["run_id"])
    op.create_index("ix_agent_change_sets_entity", "agent_change_sets", ["entity_type", "entity_id"])

    # generations.run_id: agent provenance (P2-E3-T03)
    with op.batch_alter_table("generations") as batch:
        batch.add_column(sa.Column("run_id", sa.String(36), nullable=True))
    op.create_index("ix_generations_run_id", "generations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_generations_run_id", table_name="generations")
    with op.batch_alter_table("generations") as batch:
        batch.drop_column("run_id")
    op.drop_index("ix_agent_change_sets_entity", table_name="agent_change_sets")
    op.drop_index("ix_agent_change_sets_run", table_name="agent_change_sets")
    op.drop_index("ix_agent_change_sets_project", table_name="agent_change_sets")
    op.drop_table("agent_change_sets")
    with op.batch_alter_table("agent_proposals") as batch:
        batch.drop_column("expires_at")
        batch.drop_column("irreversible")
        batch.drop_column("estimated_cost")
        batch.drop_column("estimated_tasks")
        batch.drop_column("reason")
        batch.drop_column("risk_level")
