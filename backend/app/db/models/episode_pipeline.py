"""EpisodePipeline model (C2 一键成片, mvp-spec DOC-C2).

One episode's end-to-end production run: analyze(preview) → human confirm →
shots → images → timeline → render. The row IS the durable source of truth
(stages_json records each stage's completion), so a crashed/mid-run pipeline can
be resumed from its persisted stage (断点续跑).

Design (方案 C2, 分析确认+后续自动):
- run_analysis: preview_analysis persists an immutable snapshot; pipeline stops
  at WAITING_CONFIRM with snapshot_id set.
- confirm: confirm_snapshot writes scenes → generates shot plans per scene →
  queues image generations (skipping shots that already have an image) → waits
  for those images to settle → creates/sequences the timeline → queues render.
- resume: re-runs from the first non-done stage in stages_json.

Red line: this table holds orchestration state only — all domain writes go
through the existing Services (ScriptService/GenerationService/TimelineService).
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

PIPELINE_STATUSES = ("running", "waiting_confirm", "completed", "failed")
PIPELINE_STAGES = ("analyze", "shots", "images", "timeline", "render")


class EpisodePipeline(Base):
    __tablename__ = "episode_pipelines"

    id: Mapped[str] = uuid_pk()
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    current_stage: Mapped[str | None] = mapped_column(Text)
    stages_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    snapshot_id: Mapped[str | None] = mapped_column(Text)  # pending analysis snapshot (waiting_confirm)
    error_message: Mapped[str | None] = mapped_column(Text)

    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()

    @property
    def stages(self) -> dict[str, str]:
        """Parsed stage-state map ({stage: "done"|"pending"}) — persisted as JSON."""
        import json

        return json.loads(self.stages_json or "{}")
