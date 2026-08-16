"""p8: continuity_warnings + shot_transitions (Continuity Agent + Video Bridge structure)

Revision ID: a8b9c0d1e2f3
Revises: a0b1c2d3e4f7
Create Date: 2026-08

P8-T018/T019 (Continuity Agent):

- continuity_warnings: durable store of continuity issues flagged by Rule Engine
  or the Continuity Agent's semantic check. status lifecycle open → acknowledged → fixed.
  The Agent NEVER applies fixes directly — a fix goes through agent_proposals
  (P7 Proposal system, WAITING_HUMAN approval) and applies via ShotService; on
  approve the referenced warning(s) move to 'fixed' and resolved_at is set.

P8-T021..T026 (Video Bridge structure):

- shot_transitions: structure-only for MVP — how adjacent shots connect
  (mode LAST_TO_FIRST / REFERENCE_ONLY / CUT ...) and which frame assets are
  references. Frame extraction / video generation is NOT implemented yet, so
  frame_from_asset_id / frame_to_asset_id stay NULL.

Columns per specs (database-v0.1 §20/§21, continuity-engine-design §191/§192):

  continuity_warnings: id PK, project_id FK, scene_id FK (idx), shot_id FK NULL,
    run_id NULL, category, severity(info|warning|error), message, evidence_json,
    status(open|acknowledged|fixed), created_at, resolved_at NULL.
  shot_transitions: id PK, scene_id FK, from_shot_id FK, to_shot_id FK NULL
    (NULL = scene boundary), mode, frame_from_asset_id FK NULL,
    frame_to_asset_id FK NULL, created_at.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "continuity_warnings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("scene_id", sa.String(length=36), nullable=False),
        sa.Column("shot_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"]),
    )
    op.create_index("ix_continuity_warnings_project_id", "continuity_warnings", ["project_id"])
    op.create_index("ix_continuity_warnings_scene_id", "continuity_warnings", ["scene_id"])
    op.create_index("ix_continuity_warnings_shots_id", "continuity_warnings", ["shot_id"])
    op.create_index("ix_continuity_warnings_scene_status", "continuity_warnings", ["scene_id", "status"])

    op.create_table(
        "shot_transitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scene_id", sa.String(length=36), nullable=False),
        sa.Column("from_shot_id", sa.String(length=36), nullable=False),
        sa.Column("to_shot_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("frame_from_asset_id", sa.String(length=36), nullable=True),
        sa.Column("frame_to_asset_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["from_shot_id"], ["shots.id"]),
        sa.ForeignKeyConstraint(["to_shot_id"], ["shots.id"]),
        sa.ForeignKeyConstraint(["frame_from_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["frame_to_asset_id"], ["assets.id"]),
    )
    op.create_index("ix_shot_transitions_scene_id", "shot_transitions", ["scene_id"])
    op.create_index("ix_shot_transitions_from_shot_id", "shot_transitions", ["from_shot_id"])
    op.create_index("ix_shot_transitions_scene", "shot_transitions", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_shot_transitions_scene", table_name="shot_transitions")
    op.drop_index("ix_shot_transitions_from_shot_id", table_name="shot_transitions")
    op.drop_index("ix_shot_transitions_scene_id", table_name="shot_transitions")
    op.drop_table("shot_transitions")
    op.drop_index("ix_continuity_warnings_scene_status", table_name="continuity_warnings")
    op.drop_index("ix_continuity_warnings_shots_id", table_name="continuity_warnings")
    op.drop_index("ix_continuity_warnings_scene_id", table_name="continuity_warnings")
    op.drop_index("ix_continuity_warnings_project_id", table_name="continuity_warnings")
    op.drop_table("continuity_warnings")
