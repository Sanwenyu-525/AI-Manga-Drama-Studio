"""source_documents: 设定文档库（database-v0.1 §32.6, mvp-spec DOC-001）

Project-level source-archive for setting documents (character_setting / worldview /
outline / novel_draft / other). Agent analysis injects a budgeted digest of these
so character recognition has facts to stand on.

Revision ID: e4f6a8c0d2e4
Revises: f3a5b7c9d1e3
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4f6a8c0d2e4"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=True),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("costume_id", sa.String(length=36), nullable=True),
        sa.Column("source_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["costume_id"], ["costumes.id"]),
    )
    op.create_index("ix_source_documents_project_id", "source_documents", ["project_id"])
    op.create_index("ix_source_documents_doc_type", "source_documents", ["doc_type"])


def downgrade() -> None:
    op.drop_index("ix_source_documents_doc_type", table_name="source_documents")
    op.drop_index("ix_source_documents_project_id", table_name="source_documents")
    op.drop_table("source_documents")
