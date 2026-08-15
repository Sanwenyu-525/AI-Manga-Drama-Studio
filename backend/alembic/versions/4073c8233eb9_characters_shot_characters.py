"""p1: characters + shot_characters

Revision ID: 4073c8233eb9
Revises: 395a4fdc3dfc
Create Date: 2026-08-16

P1 Character Management (database-v0.1 §7, §11): characters identity table
+ shot_characters many-to-many link table with continuity fields.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4073c8233eb9"
down_revision: Union[str, Sequence[str], None] = "395a4fdc3dfc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=True),
        sa.Column("gender", sa.Text(), nullable=True),
        sa.Column("age_description", sa.Text(), nullable=True),
        sa.Column("appearance", sa.Text(), nullable=True),
        sa.Column("personality", sa.Text(), nullable=True),
        sa.Column("visual_prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("default_costume_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_characters_project_id", "characters", ["project_id"])

    op.create_table(
        "shot_characters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shot_id", sa.String(36), sa.ForeignKey("shots.id"), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("costume_id", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("pose", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("emotion", sa.Text(), nullable=True),
        sa.Column("screen_direction", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_shot_characters_shot_id", "shot_characters", ["shot_id"])
    op.create_index("ix_shot_characters_character_id", "shot_characters", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_shot_characters_character_id", table_name="shot_characters")
    op.drop_index("ix_shot_characters_shot_id", table_name="shot_characters")
    op.drop_table("shot_characters")
    op.drop_index("ix_characters_project_id", table_name="characters")
    op.drop_table("characters")
