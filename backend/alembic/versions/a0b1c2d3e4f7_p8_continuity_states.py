"""p8: scene_continuity_states + shot_continuity_states (Continuity Engine)

Revision ID: a0b1c2d3e4f7
Revises: f7a8b9c0d1e2
Create Date: 2026-08

P8-T001 (Scene Base State) + P8-T002/T003/T004 (Shot Delta / Start / End):

- scene_continuity_states: scene_id PK FK, base_state_json (EnvironmentState +
  characters/props baseline), state_hash, computed_at, created_at, updated_at.
- shot_continuity_states: shot_id PK FK, scene_id FK (indexed), start_state_json,
  end_state_json, delta_json, dependencies_json, state_hash, warnings_json,
  recomputed_at, created_at, updated_at.

JSON columns are TEXT (deterministic canonical JSON). Timestamps TEXT ISO8601 UTC.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a0b1c2d3e4f7"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scene_continuity_states",
        sa.Column("scene_id", sa.String(length=36), primary_key=True),
        sa.Column("base_state_json", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
    )

    op.create_table(
        "shot_continuity_states",
        sa.Column("shot_id", sa.String(length=36), primary_key=True),
        sa.Column("scene_id", sa.String(length=36), nullable=False),
        sa.Column("start_state_json", sa.Text(), nullable=False),
        sa.Column("end_state_json", sa.Text(), nullable=False),
        sa.Column("delta_json", sa.Text(), nullable=False),
        sa.Column("dependencies_json", sa.Text(), nullable=False),
        sa.Column("state_hash", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("recomputed_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"]),
    )
    op.create_index("ix_shot_continuity_states_scene_id", "shot_continuity_states", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_shot_continuity_states_scene_id", table_name="shot_continuity_states")
    op.drop_table("shot_continuity_states")
    op.drop_table("scene_continuity_states")
