"""p5-e1: jobs / job_tasks / task_dependencies

Revision ID: e2f3a4b5c6d7
Revises: a7b8c9d0e1f2
Create Date: 2026-08

P5-E1 (Job / JobTask / DAG):

- jobs: a schedulable batch of generation work (e.g. "render all shots of a scene").
  status: created|queued|running|paused|completed|failed|cancelled; progress 0-100.
- job_tasks: one row per shot (or target). task_type image in MVP, video reserved.
  target_type = 'shot', target_id FK → shots.id. status queued|running|completed|failed|
  skipped|dependency_failed|cancelled. priority = shot_order (scheduling order).
  generation_id FK → generations.id (the generation this task drives).
- task_dependencies: DAG edges (task_id depends on depends_on_task_id); composite PK
  so each pair is unique and fancy fan-in/fan-out is supported.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("scene_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_index("ix_jobs_scene_id", "jobs", ["scene_id"])

    op.create_table(
        "job_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["shots.id"]),
    )
    op.create_index("ix_job_tasks_job_id", "job_tasks", ["job_id"])
    op.create_index("ix_job_tasks_target_id", "job_tasks", ["target_id"])
    op.create_index("ix_job_tasks_generation_id", "job_tasks", ["generation_id"])
    op.create_index(
        "idx_job_tasks_job_status_priority", "job_tasks", ["job_id", "status", "priority"]
    )

    op.create_table(
        "task_dependencies",
        sa.Column("task_id", sa.String(length=36), primary_key=True),
        sa.Column("depends_on_task_id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["job_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["job_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_task_dependencies_task_id", "task_dependencies", ["task_id"])
    op.create_index("ix_task_dependencies_depends_on_task_id", "task_dependencies", ["depends_on_task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_dependencies_depends_on_task_id", table_name="task_dependencies")
    op.drop_index("ix_task_dependencies_task_id", table_name="task_dependencies")
    op.drop_table("task_dependencies")
    op.drop_index("idx_job_tasks_job_status_priority", table_name="job_tasks")
    op.drop_index("ix_job_tasks_generation_id", table_name="job_tasks")
    op.drop_index("ix_job_tasks_target_id", table_name="job_tasks")
    op.drop_index("ix_job_tasks_job_id", table_name="job_tasks")
    op.drop_table("job_tasks")
    op.drop_index("ix_jobs_scene_id", table_name="jobs")
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    op.drop_table("jobs")
