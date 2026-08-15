"""p1-e1-t01: analysis idempotency keys

Revision ID: e1f2a3b4c5d6
Revises: 4073c8233eb9
Create Date: 2026-08-20

P1-E1-T01 (修复 AI 计划映射与批量写入事务): add nullable analysis keys so AI
planning persistence is idempotent and replaceable without schema-level
uniqueness (P1-E1-T02 owns DB invariants for legacy duplicates):

- episodes.analysis_key   — hash of the analyzed source text (last episode analysis)
- scenes.analysis_key     — episode analysis key; NOT NULL marks AI-created scenes
- scenes.storyboard_key   — last shot-planning key for the scene
- shots.analysis_key      — storyboard key; NOT NULL marks AI-created shots

All columns are nullable Text; manual (non-AI) rows keep NULL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "4073c8233eb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("episodes", sa.Column("analysis_key", sa.Text(), nullable=True))
    op.add_column("scenes", sa.Column("analysis_key", sa.Text(), nullable=True))
    op.add_column("scenes", sa.Column("storyboard_key", sa.Text(), nullable=True))
    op.add_column("shots", sa.Column("analysis_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("shots", "analysis_key")
    op.drop_column("scenes", "storyboard_key")
    op.drop_column("scenes", "analysis_key")
    op.drop_column("episodes", "analysis_key")
