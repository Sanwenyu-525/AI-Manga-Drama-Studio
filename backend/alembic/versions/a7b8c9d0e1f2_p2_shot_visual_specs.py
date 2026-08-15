"""p2 (P2-T005): formalize ShotVisualSpec — separate shot_visual_specs 1:1 table

Revision ID: a7b8c9d0e1f2
Revises: d6260cbe10eb
Create Date: 2026-08-16 10:00:00.000000

P2-T005 (domain-model-design #21-22, database-v0.1 §10):
- shot_visual_specs: 1:1 with shots (shot_id PRIMARY KEY/FK→shots.id). Carry the
  formalized visual spec separately from the atomic shot record: shot_type,
  camera_angle, camera_movement, composition, location_id, lighting, mood, action,
  facial_expression, environment, style_instructions, negative_instructions,
  metadata_json.
- The legacy inline shot columns (shot_type/camera_angle/camera_movement/lens/
  duration/action/emotion/environment_description/image_prompt/video_prompt/
  negative_prompt) are KEPT (marked deprecated) and are NOT data-migrated here —
  ShotService write-through keeps the spec in sync going forward; a later batch
  cleans the legacy columns once every consumer has switched to the spec.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "d6260cbe10eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shot_visual_specs",
        sa.Column("shot_id", sa.String(length=36), sa.ForeignKey("shots.id"), primary_key=True),
        sa.Column("shot_type", sa.Text(), nullable=True),
        sa.Column("camera_angle", sa.Text(), nullable=True),
        sa.Column("camera_movement", sa.Text(), nullable=True),
        sa.Column("composition", sa.Text(), nullable=True),
        sa.Column("location_id", sa.Text(), nullable=True),
        sa.Column("lighting", sa.Text(), nullable=True),
        sa.Column("mood", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("facial_expression", sa.Text(), nullable=True),
        sa.Column("environment", sa.Text(), nullable=True),
        sa.Column("style_instructions", sa.Text(), nullable=True),
        sa.Column("negative_instructions", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shot_visual_specs")
