"""p7: agent_runs + agent_proposals (persistence + proposal system)

Revision ID: f7a8b9c0d1e2
Revises: e2f3a4b5c6d7
Create Date: 2026-08

P7-T001 (AgentRun persistence):

- agent_runs: durable business record of one AI Director run. The LangGraph
  Checkpointer (thread_id = run_id) stores the graph execution state; this table
  stores the run's business fields (status, inputs, plan, result, error), so a
  GET /agent/runs/{id} survives a restart and resume can continue a run.

P7-T012/T013 (Proposal system):

- agent_proposals: a structured, human-reviewable change the agent proposes.
  status lifecycle: pending → approved|rejected → applied|conflict.

Columns per specs:
  agent_runs: id PK, project_id FK, run_type, status, current_stage,
    input_json, messages_json, plan_json, result_json, error_message,
    started_at, completed_at, created_at, updated_at.
  agent_proposals: id PK, run_id FK, tool, target_type, target_id,
    base_revision, changes_json, status, conflict_reason, error_message,
    created_at, decided_at.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("run_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("messages_json", sa.Text(), nullable=True),
        sa.Column("plan_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
    )
    op.create_index("ix_agent_proposals_run_id", "agent_proposals", ["run_id"])
    op.create_index("ix_agent_proposals_run_status", "agent_proposals", ["run_id", "status"])
    op.create_index("ix_agent_proposals_target", "agent_proposals", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_proposals_target", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_run_status", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_run_id", table_name="agent_proposals")
    op.drop_table("agent_proposals")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_project_id", table_name="agent_runs")
    op.drop_table("agent_runs")
