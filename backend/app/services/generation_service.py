"""GenerationService (backend-architecture §16, mvp-spec §68) — the boundary between
Studio and the AI generation world.

- create_generation: persist record (status=queued) + enqueue to the worker.
- retry_generation: creates a NEW record (retry_of=old) — never overwrites history (red line).
- cancel_generation / complete / fail: state transitions + events.
"""

from __future__ import annotations

import json
from datetime import UTC

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Generation, Shot
from app.domain.generation import GenerationCreate
from app.events.bus import (
    EVENT_GENERATION_CANCELLED,
    EVENT_GENERATION_CREATED,
    EVENT_GENERATION_QUEUED,
    StudioEvent,
    bus,
)
from app.repositories import ShotRepository

logger = get_logger("generations")

TERMINAL = ("completed", "failed", "cancelled")


class GenerationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotRepository(session)

    def create_generation(self, shot_id: str, data: GenerationCreate) -> Generation:
        shot = self.shots.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        # project id via shot chain
        project_id = self._project_id_of(shot)
        if project_id is None:
            raise NotFoundError("Shot has no project.", {"shot_id": shot_id})

        # P1-E2-T01: fail fast BEFORE queuing — canonical provider id, supported
        # media type, known workflow. generation.provider will equal the
        # implementation the worker actually runs.
        if data.type != "image":
            raise ValidationError(
                "Only image generation is supported in MVP.",
                {"type": data.type, "supported": ["image"]},
            )
        from app.providers.comfyui.workflow_mapper import resolve_workflow_path
        from app.providers.registry import get_image_provider

        provider = data.provider or settings.image_provider
        get_image_provider(provider)  # unknown provider → ValidationError (422)
        if data.workflow_id:
            resolve_workflow_path(data.workflow_id)  # unknown workflow → ValidationError (422)

        prompt = data.prompt or shot.image_prompt
        if not prompt:
            raise ValidationError(
                "Shot has no image_prompt. Set a prompt before generating.",
                {"shot_id": shot_id},
            )

        generation = Generation(
            project_id=project_id,
            shot_id=shot_id,
            type=data.type,
            provider=provider,
            workflow_id=data.workflow_id,
            status="queued",
            parameters=json.dumps(
                {
                    "prompt": prompt,
                    "negative_prompt": data.negative_prompt or shot.negative_prompt,
                    "seed": data.seed,
                    "width": data.width,
                    "height": data.height,
                },
                ensure_ascii=False,
            ),
            max_attempts=data.max_attempts or 1,
            progress=0,
            stage="queued",
        )
        self.session.add(generation)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_CREATED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=project_id,
                payload={"shot_id": shot_id, "status": generation.status},
            )
        )
        from app.generations.worker import enqueue_generation

        enqueue_generation(generation.id)
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_QUEUED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=project_id,
                payload={"shot_id": shot_id},
            )
        )
        logger.info("generation %s created for shot %s (provider=%s)", generation.id, shot_id, generation.provider)
        return generation

    def get_generation(self, generation_id: str) -> Generation:
        generation = self.session.get(Generation, generation_id)
        if generation is None or generation.deleted_at:
            raise NotFoundError("Generation does not exist.", {"generation_id": generation_id})
        return generation

    def list_generations(self, shot_id: str | None = None, status: str | None = None) -> list[Generation]:
        from sqlalchemy import select

        stmt = select(Generation).where(Generation.deleted_at.is_(None))
        if shot_id:
            stmt = stmt.where(Generation.shot_id == shot_id)
        if status:
            stmt = stmt.where(Generation.status == status)
        stmt = stmt.order_by(Generation.created_at.desc())
        return list(self.session.scalars(stmt))

    def list_recent(self, limit: int = 20) -> list[Generation]:
        """Recent generations across all shots (bottom dock history; P1-E4-T01:
        query lives in the Service, not the Router)."""
        from sqlalchemy import select

        stmt = (
            select(Generation)
            .where(Generation.deleted_at.is_(None))
            .order_by(Generation.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def retry_generation(self, generation_id: str) -> Generation:
        original = self.get_generation(generation_id)
        if original.status in ("queued", "running", "retrying"):
            raise ConflictError(
                "Cannot retry a generation that is still running.",
                {"generation_id": generation_id, "status": original.status},
            )
        if original.shot_id is None:
            raise ConflictError("Generation has no shot to retry.", {"generation_id": generation_id})
        params = json.loads(original.parameters or "{}")
        retry = self.create_generation(
            original.shot_id,
            GenerationCreate(
                type=original.type,
                provider=original.provider,
                workflow_id=original.workflow_id,
                prompt=params.get("prompt"),
                negative_prompt=params.get("negative_prompt"),
                seed=params.get("seed"),
                width=params.get("width"),
                height=params.get("height"),
            ),
        )
        retry.retry_of = generation_id
        self.session.commit()
        logger.info("generation %s retried as %s", generation_id, retry.id)
        return retry

    def cancel_generation(self, generation_id: str) -> Generation:
        generation = self.get_generation(generation_id)
        if generation.status in TERMINAL:
            raise ConflictError(
                "Generation already finished.",
                {"generation_id": generation_id, "status": generation.status},
            )
        generation.status = "cancelled"
        generation.completed_at = generation.completed_at or self._now()
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_CANCELLED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=generation.project_id,
                payload={"shot_id": generation.shot_id},
            )
        )
        return generation

    @staticmethod
    def _now() -> str:
        from datetime import datetime

        return datetime.now(UTC).isoformat()

    def _project_id_of(self, shot: Shot) -> str | None:
        from app.db.models import Episode, Scene

        scene = self.session.get(Scene, shot.scene_id)
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
