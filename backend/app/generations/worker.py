"""GenerationWorker (mvp-spec 搂69, backend-architecture 搂37): asyncio.Queue + worker loop.

- Jobs are submitted via enqueue_generation(generation_id).
- Worker claims records by id, loads fresh state, runs the provider, updates DB + events.
- No Redis/Celery/Temporal in MVP (mvp-spec 搂7).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import StudioError
from app.core.logging import get_logger
from app.db import session as db_session_module
from app.db.models import Generation
from app.events.bus import (
    EVENT_GENERATION_FAILED,
    EVENT_GENERATION_PROGRESS,
    EVENT_GENERATION_RETRYING,
    EVENT_GENERATION_STARTED,
    StudioEvent,
    bus,
)
from app.providers.image.base import ImageRequest
from app.providers.registry import get_image_provider
from app.services.asset_service import AssetService
from app.services.version_service import VersionService

logger = get_logger("generations.worker")

# MVP queue semantics: the DB IS the queue (database-v0.1 搂2.10 鈥?status IN ('queued','retrying')).
# The worker polls the DB periodically instead of cross-thread asyncio.Queue handoffs
# (sync routes run in a threadpool; asyncio.Queue is not thread-safe). Crash recovery is
# free: pending records are simply picked up again after restart.
POLL_INTERVAL_SECONDS = 0.5

_cancelled: set[str] = set()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def enqueue_generation(generation_id: str) -> None:
    """Wake hint (kept for API compatibility); the DB poll picks the job up regardless."""
    logger.debug("enqueue hint for %s (DB poll will claim it)", generation_id)


async def cancel_running(generation_id: str) -> None:
    """Best-effort cancel: mark cancelled; worker checks the flag before persisting output."""
    _cancelled.add(generation_id)


async def worker_loop() -> None:
    """Poll DB for queued/retrying generations and run them serially (concurrency=1)."""
    logger.info("generation worker started (db poll, concurrency=%d)", settings.generation_concurrency)
    while True:
        try:
            factory = db_session_module.session_factory_provider()
            with factory() as session:
                from sqlalchemy import select

                pending = list(
                    session.scalars(
                        select(Generation)
                        .where(Generation.deleted_at.is_(None), Generation.status.in_(("queued", "retrying")))
                        .order_by(Generation.created_at)
                        .limit(settings.generation_concurrency)
                    )
                )
            logger.debug("worker poll: %d pending", len(pending))
            for generation in pending:
                await run_generation(generation.id)
        except Exception:
            logger.exception("worker poll iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def run_generation(generation_id: str) -> None:
    factory = db_session_module.session_factory_provider()
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.deleted_at:
            logger.warning("generation %s not found; skipping", generation_id)
            return
        if generation.status in ("cancelled", "completed", "failed"):
            return
        if generation.status not in ("queued", "retrying"):
            logger.warning("generation %s in status %s; skipping", generation_id, generation.status)
            return

        generation.status = "running"
        generation.started_at = generation.started_at or _now()
        session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_STARTED,
                entity_type="generation",
                entity_id=generation.id,
                project_id=generation.project_id,
                payload={"shot_id": generation.shot_id},
            )
        )
        project_id = generation.project_id
        shot_id = generation.shot_id
        gen_id = generation.id
        provider_id = generation.provider
        params = json.loads(generation.parameters or "{}")

    # P1-E2-T01: the stored provider id IS the implementation to run — the
    # registry resolves it (unknown ids are rejected at creation, 422).
    provider = get_image_provider(provider_id)
    request = ImageRequest(
        prompt=params.get("prompt", ""),
        negative_prompt=params.get("negative_prompt"),
        seed=params.get("seed"),
        width=params.get("width"),
        height=params.get("height"),
        workflow_id=generation.workflow_id,
        metadata={"generation_id": gen_id, "shot_id": shot_id},
    )

    def _on_progress(percent: int, stage: str) -> None:
        _persist_progress(factory, gen_id, percent, stage)
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_PROGRESS,
                entity_type="generation",
                entity_id=gen_id,
                project_id=project_id,
                payload={"shot_id": shot_id, "progress": percent, "stage": stage},
            )
        )

    try:
        result = await provider.generate(request, _on_progress)
    except StudioError as exc:
        _handle_failure(factory, gen_id, project_id, shot_id, str(exc))
        return
    except Exception as exc:
        logger.exception("generation %s provider error", gen_id)
        _handle_failure(factory, gen_id, project_id, shot_id, f"Provider error: {exc}")
        return

    if gen_id in _cancelled:
        _handle_cancelled(factory, gen_id, project_id, shot_id)
        return

    if not result.success:
        _handle_failure(factory, gen_id, project_id, shot_id, result.error or "Provider returned failure.")
        return

    _persist_output(factory, gen_id, project_id, shot_id, result.output_path, result)


def _persist_progress(factory, generation_id: str, percent: int, stage: str) -> None:
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None:
            return
        generation.progress = percent
        generation.stage = stage
        session.commit()


def _persist_output(factory, generation_id: str, project_id: str, shot_id: str | None, output_path: str | None, result) -> None:
    """Attach output: Asset 鈫?MediaVersion 鈫?shot.active_image_version (mvp-spec 搂71)."""
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.status == "cancelled":
            return
        generation.progress = 100
        generation.stage = "saving"
        session.commit()

        if not output_path or not shot_id:
            generation.status = "failed"
            generation.error_message = "Provider returned no output file."
            generation.completed_at = _now()
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_FAILED,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={"shot_id": shot_id, "error": {"code": "GENERATION_FAILED", "message": "No output file."}},
                )
            )
            return

        assets = AssetService(session)
        asset = assets.register_asset(
            project_id=project_id,
            asset_type="image",
            source_path=output_path,
            shot_id=shot_id,
            source_generation_id=generation_id,
            meta={"provider": generation.provider, "params": json.loads(generation.parameters or "{}")},
        )
        version = VersionService(session).create_media_version(
            shot_id=shot_id,
            asset_id=asset.id,
            media_type="image",
            generation_id=generation_id,
            make_active=True,
        )
        generation.status = "completed"
        generation.output_asset_id = asset.id
        generation.completed_at = _now()
        generation.stage = "completed"
        session.commit()
        bus.publish(
            StudioEvent(
                event_type="generation.completed",
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={
                    "shot_id": shot_id,
                    "asset_id": asset.id,
                    "media_version_id": version.id,
                    "version_number": version.version_number,
                },
            )
        )
        logger.info("generation %s completed -> asset %s (V%d)", generation_id, asset.id, version.version_number)


def _handle_failure(factory, generation_id: str, project_id: str, shot_id: str | None, message: str) -> None:
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.status == "cancelled":
            return
        generation.attempts += 1
        if generation.attempts >= generation.max_attempts:
            generation.status = "failed"
            generation.error_message = message[:2000]
            generation.completed_at = _now()
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_FAILED,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={"shot_id": shot_id, "error": {"code": "GENERATION_FAILED", "message": message}},
                )
            )
            logger.error("generation %s failed: %s", generation_id, message)
        else:
            generation.status = "retrying"
            generation.error_message = message[:2000]
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_RETRYING,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={"shot_id": shot_id, "attempt": generation.attempts},
                )
            )
            # status is now 'retrying' 鈫?the next DB poll will claim it again


def _handle_cancelled(factory, generation_id: str, project_id: str, shot_id: str | None) -> None:
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None:
            return
        generation.status = "cancelled"
        generation.completed_at = _now()
        generation.error_message = "Cancelled by user."
        session.commit()
        bus.publish(
            StudioEvent(
                event_type="generation.cancelled",
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={"shot_id": shot_id},
            )
        )

