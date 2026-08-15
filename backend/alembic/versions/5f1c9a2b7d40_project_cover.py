"""p2: project cover image

Revision ID: 5f1c9a2b7d40
Revises: 4073c8233eb9
Create Date: 2026-08-16

Project cover upload (UI): cover_path column stores the relative path of the
cover image under the project directory (data/projects/{id}/cover.*).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f1c9a2b7d40"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("cover_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "cover_path")
