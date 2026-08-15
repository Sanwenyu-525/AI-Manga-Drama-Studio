"""GenerationWorker (mvp-spec §69, backend-architecture §37): DB-poll worker.

- The DB IS the queue: the worker claims rows with an ATOMIC conditional UPDATE
  (P1-E2-T02) — two executors can never both claim the same generation.
- Leases: a claimed row carries claim_token + lease_expires_at; the worker
  refreshes the lease on progress (heartbeat). Rows with an expired lease mean
  the previous process died — recovery re-queues them (or fails them once the
  attempt budget is exhausted).
- Retry backoff: failures go to 'retrying' with next_attempt_at = now + backoff;
  the claim query skips rows that are not due yet.
- Every status change goes through the state table (generations/state.py).
- No Redis/Celery/Temporal in MVP (mvp-spec §7).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from collections.abc import Callable

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.core.errors import StudioError
from app.core.logging import get_logger
from app.db import session as db_session_module
from app.db.models import Generation
from app.events.bus import (
    EVENT_GENERATION_COMPLETED,
    EVENT_GENERATION_FAILED,
    EVENT_GENERATION_PROGRESS,
    EVENT_GENERATION_RETRYING,
    EVENT_GENERATION_STARTED,
    StudioEvent,
    bus,
)
from app.generations.state import validate_transition
from app.providers.image.base import ImageRequest
from app.providers.registry import get_image_provider
from app.services.asset_service import AssetService
from app.services.version_service import VersionService

logger = get_logger("generations.worker")

# MVP queue semantics: the DB IS the queue (database-v0.1 §2.10 — status IN
# ('queued','retrying')). The worker polls the DB periodically instead of
# cross-thread asyncio.Queue handoffs (sync routes run in a threadpool;
# asyncio.Queue is not thread-safe).
POLL_INTERVAL_SECONDS = 0.5

_cancelled: set[str] = set()

# Worker liveness for the health check (P1-E2-T02): updated every loop iteration.
last_heartbeat: float = 0.0
WORKER_STALE_SECONDS = 15.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lease_expiry() -> str:
    return (datetime.now(UTC) + timedelta(seconds=settings.generation_lease_seconds)).isoformat()


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with a cap (P1-E2-T02): base * 2**(attempt-1), capped."""
    raw = settings.generation_retry_backoff_base * (2 ** max(0, attempt - 1))
    return min(raw, settings.generation_retry_backoff_max)


def worker_heartbeat_age_seconds() -> float | None:
    """Age of the last worker heartbeat; None when the worker never started."""
    if last_heartbeat == 0.0:
        return None
    return time.monotonic() - last_heartbeat


def enqueue_generation(generation_id: str) -> None:
    """Wake hint (kept for API compatibility); the DB poll picks the job up regardless."""
    logger.debug("enqueue hint for %s (DB poll will claim it)", generation_id)


async def cancel_running(generation_id: str) -> None:
    """Best-effort cancel: mark cancelled; worker checks the flag before persisting output."""
    _cancelled.add(generation_id)


# --- atomic claim & lease recovery (P1-E2-T02) ---

def claim_generation(session, generation_id: str) -> bool:
    """ATOMIC claim: only one executor can move queued/retrying → running.

    The WHERE clause is the single source of truth for claimability:
    status is queued/retrying, the retry backoff is due, and either the row was
    never claimed or the previous lease expired (crash recovery).
    """
    now = _now()
    stmt = (
        update(Generation)
        .where(
            Generation.id == generation_id,
            Generation.deleted_at.is_(None),
            Generation.status.in_(("queued", "retrying")),
            or_(Generation.next_attempt_at.is_(None), Generation.next_attempt_at <= now),
            or_(
                Generation.claim_token.is_(None),
                Generation.lease_expires_at.is_(None),
                Generation.lease_expires_at < now,
            ),
        )
        .values(
            status="running",
            claim_token=str(uuid.uuid4()),
            claimed_at=now,
            lease_expires_at=_lease_expiry(),
            started_at=Generation.started_at,  # keep first start on retries
            next_attempt_at=None,
            progress=0,
            stage="running",
        )
        .execution_options(synchronize_session=False)
    )
    result = session.execute(stmt)
    return result.rowcount == 1


def recover_expired_leases(factory=None) -> int:
    """Crash recovery: running rows whose lease expired are re-queued (or failed
    when the attempt budget is exhausted). Returns the number of rows handled."""
    f = factory or db_session_module.session_factory_provider()
    recovered = 0
    with f() as session:
        stale = list(
            session.scalars(
                select(Generation).where(
                    Generation.deleted_at.is_(None),
                    Generation.status == "running",
                    Generation.lease_expires_at.is_not(None),
                    Generation.lease_expires_at < _now(),
                )
            )
        )
        for generation in stale:
            generation.attempts += 1
            if generation.attempts >= generation.max_attempts:
                validate_transition(generation.status, "failed")
                generation.status = "failed"
                generation.error_message = "Worker lease expired (crash recovery); attempt budget exhausted."
                generation.completed_at = _now()
            else:
                validate_transition(generation.status, "queued")
                generation.status = "queued"
                generation.claim_token = None
                generation.error_message = "Worker lease expired; re-queued for recovery."
            recovered += 1
        if stale:
            session.commit()
    if recovered:
        logger.warning("lease recovery: handled %d stale running generations", recovered)
    return recovered


async def worker_loop() -> None:
    """Poll DB for claimable generations and run them serially (concurrency=1)."""
    global last_heartbeat
    last_heartbeat = time.monotonic()
    logger.info("generation worker started (db poll, concurrency=%d)", settings.generation_concurrency)
    while True:
        last_heartbeat = time.monotonic()
        try:
            recover_expired_leases()
            factory = db_session_module.session_factory_provider()
            with factory() as session:
                now = _now()
                pending = list(
                    session.scalars(
                        select(Generation)
                        .where(
                            Generation.deleted_at.is_(None),
                            Generation.status.in_(("queued", "retrying")),
                            or_(Generation.next_attempt_at.is_(None), Generation.next_attempt_at <= now),
                        )
                        .order_by(Generation.created_at)
                        .limit(settings.generation_concurrency)
                    )
                )
            logger.debug("worker poll: %d pending", len(pending))
            for generation in pending:
                await run_generation(generation.id)
        except Exception:  # noqa: BLE001 — worker must never die
            logger.exception("worker poll iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def run_generation(generation_id: str) -> None:
    factory = db_session_module.session_factory_provider()
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.deleted_at:
            logger.warning("generation %s not found; skipping", generation_id)
            return
        if not claim_generation(session, generation_id):
            logger.debug("generation %s not claimable; skipping", generation_id)
            return
        session.commit()
        generation = session.get(Generation, generation_id)  # fresh post-claim state
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
        workflow_id = generation.workflow_id
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
        workflow_id=workflow_id,
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
    except Exception as exc:  # noqa: BLE001
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


def _persist_progress(factory: Callable, generation_id: str, percent: int, stage: str) -> None:
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None:
            return
        generation.progress = percent
        generation.stage = stage
        generation.lease_expires_at = _lease_expiry()  # heartbeat: extend the lease
        session.commit()


def _persist_output(factory: Callable, generation_id: str, project_id: str, shot_id: str | None, output_path: str | None, result) -> None:
    """Attach output in ONE transaction (ADR-001 2.4 / P1-E2-T03): Asset registration +
    version assignment + shot active pointer + generation completion commit together.

    Events are published after the commit (commit-then-publish red line).
    """
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.status == "cancelled":
            return
        generation.progress = 100
        generation.stage = "saving"
        session.flush()

        if not output_path or not shot_id:
            validate_transition(generation.status, "failed")
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
            generation_id=generation_id,
            meta={"provider": generation.provider, "params": json.loads(generation.parameters or "{}")},
            commit=False,  # caller-owned transaction
        )
        version = VersionService(session).assign_version(
            shot_id=shot_id,
            asset=asset,
            media_type="image",
            make_active=True,
            commit=False,  # caller-owned transaction
        )
        validate_transition(generation.status, "completed")
        generation.status = "completed"
        generation.output_asset_id = asset.id
        generation.completed_at = _now()
        generation.stage = "completed"
        session.commit()

        bus.publish(
            StudioEvent(
                event_type="asset.created",
                entity_type="asset",
                entity_id=asset.id,
                project_id=project_id,
                payload={"type": asset.type, "shot_id": shot_id},
            )
        )
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_COMPLETED,
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={
                    "shot_id": shot_id,
                    "asset_id": asset.id,
                    "version_number": version.version_number,
                },
            )
        )
        logger.info("generation %s completed -> asset %s (V%d)", generation_id, asset.id, version.version_number)


def _handle_failure(factory: Callable, generation_id: str, project_id: str, shot_id: str | None, message: str) -> None:
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.status == "cancelled":
            return
        generation.attempts += 1
        if generation.attempts >= generation.max_attempts:
            validate_transition(generation.status, "failed")
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
            validate_transition(generation.status, "retrying")
            generation.status = "retrying"
            generation.error_message = message[:2000]
            generation.claim_token = None  # release the claim
            generation.next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=_backoff_seconds(generation.attempts))
            ).isoformat()
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
            # status is now 'retrying' with a backoff gate — the next poll claims it
            # only after next_attempt_at (P1-E2-T02).


def _handle_cancelled(factory: Callable, generation_id: str, project_id: str, shot_id: str | None) -> None:
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None:
            return
        validate_transition(generation.status, "cancelled")
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
