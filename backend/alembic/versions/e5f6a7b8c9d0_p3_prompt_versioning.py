"""p3 (ADR-002): prompt versioning — prompts / prompt_versions tables

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-08

ADR-002 (docs/adr/ADR-002-prompt-versioning.md):
- prompts (per target per prompt_type, authoritative active_version_id) and
  prompt_versions (immutable version chain) tables.
- shots.active_prompt_version_id: convenience pointer (image prompt priority).
- generations.prompt_version_id: provenance for generation inputs.
- shot.image_prompt/video_prompt/negative_prompt columns stay as a DEPRECATED
  write-through cache, synced by PromptService.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "prompts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("prompt_type", sa.Text(), nullable=False),
        sa.Column("active_version_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_prompts_target", "prompts", ["target_type", "target_id"])
    op.create_index("idx_prompts_type", "prompts", ["target_type", "target_id", "prompt_type"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("prompt_id", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("positive_prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("structured_spec_json", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("generated_by", sa.Text(), nullable=True),
        sa.Column("parent_version_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "uq_prompt_versions_prompt_number", "prompt_versions",
        ["prompt_id", "version_number"], unique=True,
    )
    op.create_index("idx_prompt_versions_prompt", "prompt_versions", ["prompt_id", "version_number"])

    with op.batch_alter_table("shots") as batch:
        batch.add_column(sa.Column("active_prompt_version_id", sa.Text(), nullable=True))
    with op.batch_alter_table("generations") as batch:
        batch.add_column(sa.Column("prompt_version_id", sa.Text(), nullable=True))

    # backfill: shot inline prompts -> prompt v1 rows
    # (shots carry no project_id — resolve via scenes -> episodes)
    shots = bind.execute(
        sa.text(
            "SELECT s.id, e.project_id, s.image_prompt, s.video_prompt, s.negative_prompt "
            "FROM shots s "
            "JOIN scenes sc ON sc.id = s.scene_id "
            "JOIN episodes e ON e.id = sc.episode_id "
            "WHERE s.deleted_at IS NULL"
        )
    ).fetchall()
    for shot_id, project_id, image_prompt, video_prompt, negative_prompt in shots:
        for prompt_type, positive in (("SHOT_IMAGE", image_prompt), ("SHOT_VIDEO", video_prompt)):
            if not positive:
                continue
            prompt_id = f"prompt_{shot_id}_{prompt_type.lower()}"[:36]
            version_id = f"pv_{shot_id}_{prompt_type.lower()}_1"[:36]
            bind.execute(
                sa.text(
                    "INSERT INTO prompts (id, project_id, target_type, target_id, prompt_type, active_version_id, created_at, updated_at) "
                    "VALUES (:id, :pid, 'SHOT', :sid, :pt, :vid, :ts, :ts)"
                ),
                {"id": prompt_id, "pid": project_id, "sid": shot_id, "pt": prompt_type, "vid": version_id, "ts": "2026-08-01T00:00:00+00:00"},
            )
            bind.execute(
                sa.text(
                    "INSERT INTO prompt_versions (id, prompt_id, version_number, positive_prompt, negative_prompt, generated_by, created_at) "
                    "VALUES (:id, :pid, 1, :pos, :neg, 'migration', :ts)"
                ),
                {"id": version_id, "pid": prompt_id, "pos": positive, "neg": negative_prompt if prompt_type == "SHOT_IMAGE" else None, "ts": "2026-08-01T00:00:00+00:00"},
            )
            if prompt_type == "SHOT_IMAGE":
                bind.execute(
                    sa.text("UPDATE shots SET active_prompt_version_id = :vid WHERE id = :sid"),
                    {"vid": version_id, "sid": shot_id},
                )


def downgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.drop_column("prompt_version_id")
    with op.batch_alter_table("shots") as batch:
        batch.drop_column("active_prompt_version_id")
    op.drop_index("idx_prompt_versions_prompt", table_name="prompt_versions")
    op.drop_index("uq_prompt_versions_prompt_number", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("idx_prompts_type", table_name="prompts")
    op.drop_index("idx_prompts_target", table_name="prompts")
    op.drop_table("prompts")
