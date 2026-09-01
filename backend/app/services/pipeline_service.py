"""PipelineService (C2 一键成片, mvp-spec DOC-C2).

One episode's end-to-end production run with the agreed 分析确认+后续自动 design:
- run_analysis: preview_analysis → WAITING_CONFIRM (snapshot_id + plans for review).
- confirm: confirm_snapshot (scenes) → shot plans per scene → queue image
  generations (skip shots that already have an image) → running/images.
- finalize: create/sequence timeline → queue render → completed.
- resume: continue from the first non-done stage (stages_json is the durable
  source of truth; confirm_snapshot is idempotent so replaying is safe).

All domain writes go through existing Services (red line): ScriptService,
GenerationService, TimelineService, RenderService. This service only orchestrates.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Episode, EpisodePipeline, Scene, Shot
from app.domain.generation import GenerationCreate
from app.domain.pipeline import PIPELINE_STAGES, PipelineRead, PipelineRunRead
from app.events.bus import StudioEvent, bus
from app.services.script_service import ScriptService

logger = get_logger("pipeline")

_EVENT_PIPELINE_UPDATED = "pipeline.updated"


class PipelineService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ reads

    def latest(self, episode_id: str) -> PipelineRead | None:
        stmt = (
            select(EpisodePipeline)
            .where(EpisodePipeline.episode_id == episode_id, EpisodePipeline.deleted_at.is_(None))
            .order_by(EpisodePipeline.created_at.desc())
            .limit(1)
        )
        pipeline = self.session.scalars(stmt).first()
        return self._read(pipeline) if pipeline is not None else None

    def get(self, pipeline_id: str) -> PipelineRead:
        pipeline = self._get(pipeline_id)
        return self._read(pipeline)

    def get_or_create(self, episode_id: str) -> EpisodePipeline:
        """Active (not completed) pipeline for the episode, or a fresh one."""
        episode = self.session.get(Episode, episode_id)
        if episode is None or episode.deleted_at:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        existing = self.latest(episode_id)
        if existing is not None and existing.status != "completed":
            return self._get(existing.id)
        pipeline = EpisodePipeline(
            episode_id=episode_id,
            project_id=episode.project_id,
            status="running",
            stages_json=json.dumps({s: "pending" for s in PIPELINE_STAGES}),
        )
        self.session.add(pipeline)
        self.session.commit()
        self._publish(pipeline)
        logger.info("pipeline %s created for episode %s", pipeline.id, episode_id)
        return pipeline

    # -------------------------------------------------------------- run / confirm

    async def run_analysis(self, episode_id: str, llm) -> PipelineRunRead:
        """Analysis preview → WAITING_CONFIRM with the reviewed plans + snapshot_id."""
        pipeline = self.get_or_create(episode_id)
        preview = await ScriptService(self.session, llm).preview_analysis(episode_id)
        pipeline.snapshot_id = preview.snapshot_id
        self._set_stage(pipeline, "analyze", "done")
        pipeline.current_stage = None
        pipeline.status = "waiting_confirm"
        pipeline.error_message = None
        self.session.commit()
        self._publish(pipeline)
        logger.info("pipeline %s waiting_confirm (snapshot %s)", pipeline.id, preview.snapshot_id)
        return PipelineRunRead(pipeline=self._read(pipeline), plans=preview.plans)

    async def confirm(self, pipeline_id: str, snapshot_id: str | None, llm) -> PipelineRunRead:
        """Confirm the reviewed analysis → scenes → shots → queue images."""
        pipeline = self._get(pipeline_id)
        if pipeline.status == "completed":
            return PipelineRunRead(pipeline=self._read(pipeline))
        if pipeline.stages.get("analyze") != "done":
            raise ValidationError(
                "Pipeline has no analysis. Run the pipeline (analysis) first.",
                {"pipeline_id": pipeline_id},
            )
        sid = (snapshot_id or "").strip() or pipeline.snapshot_id
        if not sid:
            raise ValidationError(
                "Pipeline has no analysis snapshot to confirm.",
                {"pipeline_id": pipeline_id},
            )

        await self._ensure_scenes_shots(pipeline, llm, sid)
        pending = await self._ensure_images(pipeline)
        return PipelineRunRead(pipeline=self._read(pipeline), pending_shot_ids=pending)

    async def resume(self, pipeline_id: str, llm) -> PipelineRunRead:
        """Continue from the first non-done stage (crash/mid-run recovery)."""
        pipeline = self._get(pipeline_id)
        if pipeline.status == "completed":
            return PipelineRunRead(pipeline=self._read(pipeline))
        if pipeline.stages.get("analyze") != "done":
            return await self.run_analysis(pipeline.episode_id, llm)

        sid = pipeline.snapshot_id
        if not sid:
            raise ValidationError(
                "Pipeline has no analysis snapshot; cannot resume.",
                {"pipeline_id": pipeline_id},
            )
        if pipeline.stages.get("shots") != "done" or pipeline.stages.get("images") != "done":
            await self._ensure_scenes_shots(pipeline, llm, sid)
            await self._ensure_images(pipeline)
            return PipelineRunRead(pipeline=self._read(pipeline))
        if pipeline.stages.get("timeline") != "done" or pipeline.stages.get("render") != "done":
            self.finalize(pipeline_id)
        return PipelineRunRead(pipeline=self._read(pipeline))

    def finalize(self, pipeline_id: str) -> PipelineRunRead:
        """Create/sequence the timeline and queue the episode render → completed."""
        pipeline = self._get(pipeline_id)
        if pipeline.status == "completed":
            return PipelineRunRead(pipeline=self._read(pipeline))

        episode_id = pipeline.episode_id
        from app.services.render_service import RenderService
        from app.services.timeline_service import TimelineService

        timeline = self._timeline_of(episode_id)
        if timeline is None:
            TimelineService(self.session).create_timeline(episode_id)
            timeline = self._timeline_of(episode_id)
        if timeline is None:
            raise ValidationError("Timeline could not be created.", {"episode_id": episode_id})
        TimelineService(self.session).sequence_from_shots(timeline.id)
        self._set_stage(pipeline, "timeline", "done")

        RenderService(self.session).create_render_generation(timeline.id)
        self._set_stage(pipeline, "render", "done")

        pipeline.status = "completed"
        pipeline.current_stage = None
        self.session.commit()
        self._publish(pipeline)
        logger.info("pipeline %s completed (episode %s)", pipeline.id, episode_id)
        return PipelineRunRead(pipeline=self._read(pipeline))

    # ---------------------------------------------------------------- stages

    async def _ensure_scenes_shots(self, pipeline: EpisodePipeline, llm, snapshot_id: str) -> None:
        """Scenes from the confirmed snapshot + shot plans per scene (idempotent)."""
        if pipeline.stages.get("shots") == "done":
            return
        service = ScriptService(self.session, llm)
        # confirm_snapshot is idempotent (replays on an already-confirmed snapshot)
        await service.confirm_snapshot(pipeline.episode_id, snapshot_id)
        self._set_stage(pipeline, "shots", "done")
        self.session.commit()
        for scene in self._scenes_of(pipeline.episode_id):
            await service.generate_shot_plans(scene.id)
        self.session.commit()
        self._publish(pipeline)
        logger.info("pipeline %s shots stage done (%d scenes)", pipeline.id, len(self._scenes_of(pipeline.episode_id)))

    async def _ensure_images(self, pipeline: EpisodePipeline) -> list[str]:
        """Queue one image generation per shot without an active image (idempotent)."""
        if pipeline.stages.get("images") == "done":
            return []
        from app.services.generation_service import GenerationService

        pending: list[str] = []
        for shot in self._shots_of(pipeline.episode_id):
            if shot.active_image_asset_id is None:
                try:
                    GenerationService(self.session).create_generation(
                        shot.id, GenerationCreate(type="image")
                    )
                except ConflictError:
                    # A generation for this shot is already queued/running (e.g.
                    # resume raced an in-flight queue) — it counts as covered.
                    pass
                else:
                    pending.append(shot.id)
        self._set_stage(pipeline, "images", "done")
        pipeline.current_stage = "images"
        pipeline.status = "running"
        self.session.commit()
        self._publish(pipeline)
        logger.info("pipeline %s images stage: queued %d", pipeline.id, len(pending))
        return pending

    # ---------------------------------------------------------------- helpers

    def _set_stage(self, pipeline: EpisodePipeline, stage: str, state: str) -> None:
        stages = pipeline.stages
        stages[stage] = state
        pipeline.stages_json = json.dumps(stages, ensure_ascii=False)

    def _scenes_of(self, episode_id: str) -> list[Scene]:
        return list(
            self.session.scalars(
                select(Scene)
                .where(Scene.episode_id == episode_id, Scene.deleted_at.is_(None))
                .order_by(Scene.scene_number)
            )
        )

    def _shots_of(self, episode_id: str) -> list[Shot]:
        return list(
            self.session.scalars(
                select(Shot)
                .join(Scene, Shot.scene_id == Scene.id)
                .where(Scene.episode_id == episode_id, Shot.deleted_at.is_(None))
                .order_by(Scene.scene_number, Shot.shot_number)
            )
        )

    def _timeline_of(self, episode_id: str):
        from app.db.models import Timeline

        return self.session.scalars(
            select(Timeline).where(Timeline.episode_id == episode_id)
        ).first()

    def _get(self, pipeline_id: str) -> EpisodePipeline:
        pipeline = self.session.scalars(
            select(EpisodePipeline).where(
                EpisodePipeline.id == pipeline_id, EpisodePipeline.deleted_at.is_(None)
            )
        ).first()
        if pipeline is None:
            raise NotFoundError("Pipeline does not exist.", {"pipeline_id": pipeline_id})
        return pipeline

    def _read(self, pipeline: EpisodePipeline) -> PipelineRead:
        return PipelineRead(
            id=pipeline.id,
            episode_id=pipeline.episode_id,
            project_id=pipeline.project_id,
            status=pipeline.status,
            current_stage=pipeline.current_stage,
            stages=json.loads(pipeline.stages_json or "{}"),
            snapshot_id=pipeline.snapshot_id,
            error_message=pipeline.error_message,
            created_at=pipeline.created_at,
            updated_at=pipeline.updated_at,
        )

    def _publish(self, pipeline: EpisodePipeline) -> None:
        bus.publish(
            StudioEvent(
                event_type=_EVENT_PIPELINE_UPDATED,
                entity_type="pipeline",
                entity_id=pipeline.id,
                project_id=pipeline.project_id,
                payload={
                    "episode_id": pipeline.episode_id,
                    "status": pipeline.status,
                    "current_stage": pipeline.current_stage,
                    "stages": json.loads(pipeline.stages_json or "{}"),
                },
            )
        )
