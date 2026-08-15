"""p3 (P3-T012/T013): generation provenance — generation_inputs / generation_outputs

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08

ADR-001 §3 / P3-T012-T013 (accepted):
- generation_inputs: what a generation consumed (prompt version, shot ref, and
  later character/location refs). sparse rows: reference columns optional.
- generation_outputs: what a generation produced. PRIMARY KEY(generation_id, asset_id)
  lets one generation fan out to multiple assets while answering
  "this asset came from which generation" and "this generation made which assets".
- Both are inserted inside the generation write path (single-commit completion for
  outputs per ADR-001 2.4).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_inputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("generation_id", sa.Text(), nullable=False),
        sa.Column("input_type", sa.Text(), nullable=False),
        sa.Column("reference_type", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Float(), nullable=False, server_default=sa.text("1000")),
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )
    op.create_index("idx_generation_inputs_gen", "generation_inputs", ["generation_id"])

    op.create_table(
        "generation_outputs",
        sa.Column("generation_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Float(), nullable=False, server_default=sa.text("1000")),
        sa.PrimaryKeyConstraint("generation_id", "asset_id"),
    )
    op.create_index("idx_generation_outputs_asset", "generation_outputs", ["asset_id"])


def downgrade() -> None:
    op.drop_index("idx_generation_outputs_asset", table_name="generation_outputs")
    op.drop_table("generation_outputs")
    op.drop_index("idx_generation_inputs_gen", table_name="generation_inputs")
    op.drop_table("generation_inputs")
