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

from sqlalchemy import func, or_, select, update

from app.core.config import settings
from app.core.errors import StudioError
from app.core.logging import get_logger
from app.db import session as db_session_module
from app.db.models import Generation, GenerationOutput
from app.events.bus import (
    EVENT_GENERATION_COMPLETED,
    EVENT_GENERATION_FAILED,
    EVENT_GENERATION_INTERRUPTED,
    EVENT_GENERATION_PROGRESS,
    EVENT_GENERATION_RETRYING,
    EVENT_GENERATION_STARTED,
    EVENT_TIMELINE_RENDERED,
    StudioEvent,
    bus,
)
from app.generations.retry_policy import RetryOutcome, classify_failure
from app.generations.state import validate_transition
from app.providers.audio.base import AudioRequest
from app.providers.image.base import ImageRequest
from app.providers.registry import get_audio_provider, get_image_provider, get_render_provider
from app.providers.render.base import RenderClip, RenderRequest
from app.services.asset_service import AssetService
from app.services.version_service import VersionService

logger = get_logger("generations.worker")

# MVP queue semantics: the DB IS the queue (database-v0.1 §2.10 — status IN
# ('queued','retrying')). The worker polls the DB periodically instead of
# cross-thread asyncio.Queue handoffs (sync routes run in a threadpool;
# asyncio.Queue is not thread-safe).
POLL_INTERVAL_SECONDS = 0.5

_cancelled: set[str] = set()

# P5-T013/T014: queue-level pause — only stops *scheduling new tasks*; running jobs
# finish, and lease recovery keeps running while paused.
_paused: bool = False

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
    """Best-effort cancel of a RUNNING generation.

    - Adds the id to the in-memory hint set (worker checks it before persisting).
    - Asks the provider to interrupt its ComfyUI job (best-effort; never raises).
    Note: the durable 'cancelling' state is set by GenerationService.cancel_generation —
    this function only orchestrates the provider interrupt + memory hint.
    """
    _cancelled.add(generation_id)
    try:
        factory = db_session_module.session_factory_provider()
        with factory() as session:
            generation = session.get(Generation, generation_id)
            provider_ref = generation.provider_ref if generation else None
        if provider_ref:
            provider = get_image_provider()
            await provider.cancel(provider_ref)
    except Exception:  # noqa: BLE001 — provider cancel is best-effort
        logger.exception("best-effort provider cancel failed for generation %s", generation_id)


# --- queue pause / resume / status (P5-T013/T014) ---

def pause_queue() -> None:
    """Pause scheduling of NEW tasks; running generations continue to completion."""
    global _paused
    _paused = True
    logger.info("generation queue paused")


def resume_queue() -> None:
    """Resume scheduling of new tasks."""
    global _paused
    _paused = False
    logger.info("generation queue resumed")


def is_paused() -> bool:
    """Whether new-task scheduling is paused."""
    return _paused


def queue_status(factory=None) -> dict:
    """Queue-level status for GET /generations/queue-status.

    paused        — are new tasks being scheduled?
    pending       — claimable rows (queued/retrying, backoff due)
    pending_total — all queued/retrying rows (including those held by backoff)
    running       — rows the worker currently claims (lease not expired)
    """
    f = factory or db_session_module.session_factory_provider()
    now = _now()
    with f() as session:
        pending_total = session.scalar(
            select(func.count()).select_from(Generation).where(
                Generation.deleted_at.is_(None),
                Generation.status.in_(("queued", "retrying")),
            )
        ) or 0
        pending = session.scalar(
            select(func.count()).select_from(Generation).where(
                Generation.deleted_at.is_(None),
                Generation.status.in_(("queued", "retrying")),
                or_(Generation.next_attempt_at.is_(None), Generation.next_attempt_at <= now),
            )
        ) or 0
        running = session.scalar(
            select(func.count()).select_from(Generation).where(
                Generation.deleted_at.is_(None),
                Generation.status == "running",
            )
        ) or 0
    return {
        "paused": _paused,
        "pending": pending,
        "pending_total": pending_total,
        "running": running,
    }


def reset_worker_state() -> None:
    """Test hook: clear process-level pause/cancel state between tests."""
    global _paused
    _paused = False
    _cancelled.clear()


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
                    Generation.status.in_(("running", "cancelling")),
                    Generation.lease_expires_at.is_not(None),
                    Generation.lease_expires_at < _now(),
                )
            )
        )
        interrupted_ids: list[tuple[str, str, str | None]] = []
        cancelled_ids: list[tuple[str, str, str | None]] = []
        for generation in stale:
            if generation.status == "cancelling":
                # The cancelling process died before it could finalize — conclude the
                # user's cancel now (durable across restart).
                validate_transition(generation.status, "cancelled")
                generation.status = "cancelled"
                generation.completed_at = _now()
                generation.error_message = "Cancelled by user (finalized after restart)."
                generation.stage = "cancelled"
                cancelled_ids.append((generation.id, generation.project_id, generation.shot_id))
                recovered += 1
                continue
            generation.attempts += 1
            if generation.attempts >= generation.max_attempts:
                # P5-T016: exhausted attempt budget after a crash is a SYSTEM
                # interruption (abnormal-task detection), not a user failure → 'interrupted'
                # (a terminal state distinct from 'failed').
                validate_transition(generation.status, "interrupted")
                generation.status = "interrupted"
                generation.error_message = (
                    "Worker lease expired (crash recovery); attempt budget exhausted (interrupted)."
                )
                generation.completed_at = _now()
                interrupted_ids.append((generation.id, generation.project_id, generation.shot_id))
            else:
                validate_transition(generation.status, "queued")
                generation.status = "queued"
                generation.claim_token = None
                generation.error_message = "Worker lease expired; re-queued for recovery."
            recovered += 1
        if stale:
            session.commit()
        # commit-then-publish (red line): emit events only after commit.
        for gen_id, project_id, shot_id in interrupted_ids:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_INTERRUPTED,
                    entity_type="generation",
                    entity_id=gen_id,
                    project_id=project_id,
                    payload={"shot_id": shot_id},
                )
            )
            logger.warning("generation %s interrupted (lease expired, budget exhausted)", gen_id)
        for gen_id, project_id, shot_id in cancelled_ids:
            bus.publish(
                StudioEvent(
                    event_type="generation.cancelled",
                    entity_type="generation",
                    entity_id=gen_id,
                    project_id=project_id,
                    payload={"shot_id": shot_id},
                )
            )
            logger.info("generation %s cancelled (finalized after restart)", gen_id)
    if recovered:
        logger.warning("lease recovery: handled %d stale generations", recovered)
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
            # P5-T013: while paused we still poll + recover leases, but we do NOT
            # schedule new tasks. The worker never sleeps waiting for resume — it
            # keeps polling so resume is picked up on the next iteration.
            if _paused:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
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

    # Phase 9 (P9-E3): episode render generations are executed through the
    # RenderProvider (mock MJPEG-AVI / ffmpeg) instead of the image path.
    if generation.type == "render":
        await _run_render_generation(factory, gen_id, project_id, provider_id, params)
        return

    # TASK-012: type="audio" (voiceover) runs through the AudioProvider and its
    # output registers as an AUDIO asset re-bound to the source timeline clip.
    if generation.type == "audio":
        await _run_audio_generation(factory, gen_id, project_id, provider_id, params)
        return

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
        _handle_failure(factory, gen_id, project_id, shot_id, str(exc), exc=exc)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("generation %s provider error", gen_id)
        _handle_failure(factory, gen_id, project_id, shot_id, f"Provider error: {exc}", exc=exc)
        return

    if gen_id in _cancelled or _db_status(factory, gen_id) == "cancelling":
        # P5-T015: cancel is durable — check the persisted 'cancelling' marker (survives
        # restart) in addition to the in-memory hint set.
        _handle_cancelled(factory, gen_id, project_id, shot_id)
        return

    if not result.success:
        # An unsuccessful result is deterministic — NonRetryable (P5-T009), fail fast.
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
        # P5-T015: if the user cancelled (durable 'cancelling' or in-memory hint) while
        # we were finishing, do NOT persist output — finalize as cancelled instead.
        if generation is None or generation.status == "cancelled":
            return
        if generation.status == "cancelling" or generation.id in _cancelled:
            session.commit()
            _handle_cancelled(factory, generation_id, project_id, shot_id)
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
        # P3-T012: record the produced asset in generation_outputs (same TX).
        session.add(
            GenerationOutput(
                generation_id=generation_id,
                asset_id=asset.id,
                role="primary",
                order_index=1000,
            )
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


def _db_status(factory: Callable, generation_id: str) -> str | None:
    """Read a generation's current status (used to make cancel durable across restarts)."""
    with factory() as session:
        generation = session.get(Generation, generation_id)
        return generation.status if generation else None


def _handle_failure(
    factory: Callable,
    generation_id: str,
    project_id: str,
    shot_id: str | None,
    message: str,
    exc: BaseException | None = None,
) -> None:
    """Route a failure by retry classification (P5-T009):

    - Retryable    → existing retrying + exponential backoff path.
    - NonRetryable → immediate 'failed' — we do NOT burn the attempt budget.
    - UserActionRequired is treated as NonRetryable (clear failed message; no new state).
    A generation the user is cancelling ('cancelling' / in the hint set) is finalized
    to 'cancelled' instead of being retried or failed.
    """
    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None:
            return
        if generation.status == "cancelling" or generation.id in _cancelled:
            return  # cancel in flight — run_generation finalizes to 'cancelled'
        if generation.status == "cancelled":
            return
        outcome = classify_failure(exc, message)
        retryable = outcome is RetryOutcome.RETRYABLE
        generation.error_message = message[:2000]

        if not retryable:
            # NonRetryable → fail fast, no attempt-budget churn.
            validate_transition(generation.status, "failed")
            generation.status = "failed"
            generation.completed_at = _now()
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_FAILED,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={
                        "shot_id": shot_id,
                        "retryable": False,
                        "error": {"code": "GENERATION_FAILED", "message": message},
                    },
                )
            )
            logger.error("generation %s failed (non-retryable): %s", generation_id, message)
            return

        generation.attempts += 1
        if generation.attempts >= generation.max_attempts:
            validate_transition(generation.status, "failed")
            generation.status = "failed"
            generation.completed_at = _now()
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_FAILED,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={
                        "shot_id": shot_id,
                        "retryable": True,
                        "error": {"code": "GENERATION_FAILED", "message": message},
                    },
                )
            )
            logger.error("generation %s failed after %d attempts: %s", generation_id, generation.attempts, message)
        else:
            validate_transition(generation.status, "retrying")
            generation.status = "retrying"
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
        if generation is None or generation.status in ("cancelled", "completed"):
            return
        # P5-T015: the row may already be durably 'cancelling' (set by the API while the
        # job was running) → cancelling→cancelled; or still 'running' (memory-hint path)
        # → running→cancelled. Both are legal transitions.
        validate_transition(generation.status, "cancelled")
        generation.status = "cancelled"
        generation.completed_at = _now()
        generation.error_message = "Cancelled by user."
        generation.stage = "cancelled"
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
        _cancelled.discard(generation_id)

# ------------------------------------------------------------------ render (Phase 9)


async def _run_render_generation(
    factory: Callable,
    generation_id: str,
    project_id: str,
    provider_id: str,
    params: dict,
) -> None:
    """Execute a type='render' generation: resolve sources, call the RenderProvider,
    persist the FINAL_VIDEO asset on success (or route failures through the shared
    retry/failure helpers)."""
    provider = get_render_provider(provider_id)
    width = int(params.get("width") or 720)
    height = int(params.get("height") or 1280)
    fps = float(params.get("fps") or 24.0)
    out_dir = settings.data_dir / "render_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(out_dir / (f"gen_{generation_id}_out" + (".mp4" if provider.name == "ffmpeg" else ".avi")))

    requests = []
    audio_requests = []
    subtitle_requests = []
    skipped = 0
    with factory() as session:
        from app.db.models import Asset
        from app.services.asset_service import AssetService

        asset_svc = AssetService(session)
        for c in params.get("clips", []):
            asset = session.get(Asset, c.get("asset_id")) if c.get("asset_id") else None
            if asset is None or asset.deleted_at:
                skipped += 1
                continue
            try:
                source = str(asset_svc.absolute_path(asset))
            except Exception:  # noqa: BLE001 — missing/broken file → skip clip
                skipped += 1
                continue
            requests.append(
                RenderClip(
                    source_path=source,
                    kind=c.get("kind") or ("image" if asset.type == "image" else "video"),
                    start=float(c.get("start") or 0),
                    end=float(c.get("end") or 0),
                    source_in=float(c.get("source_in") or 0),
                    source_out=c.get("source_out"),
                    text=c.get("text"),
                )
            )
        for c in params.get("audio_clips", []):  # TASK-013: VOICE/MUSIC/SFX bed
            asset = session.get(Asset, c.get("asset_id")) if c.get("asset_id") else None
            if asset is None or asset.deleted_at:
                skipped += 1
                continue
            try:
                source = str(asset_svc.absolute_path(asset))
            except Exception:  # noqa: BLE001 — missing/broken file → skip clip
                skipped += 1
                continue
            audio_requests.append(
                RenderClip(
                    source_path=source,
                    kind="audio",
                    start=float(c.get("start") or 0),
                    end=float(c.get("end") or 0),
                    source_in=float(c.get("source_in") or 0),
                    source_out=c.get("source_out"),
                )
            )
        for c in params.get("subtitle_clips", []):  # TASK-013: burned captions
            text = (c.get("text") or "").strip()
            if not text:
                continue
            subtitle_requests.append(
                RenderClip(
                    source_path="",
                    kind="subtitle",
                    start=float(c.get("start") or 0),
                    end=float(c.get("end") or 0),
                    text=text,
                )
            )
    if not requests:
        _handle_failure(
            factory, generation_id, project_id, None,
            "No renderable clip sources found (missing asset files).",
        )
        return

    request = RenderRequest(
        output_path=output_path,
        width=width,
        height=height,
        fps=fps,
        clips=requests,
        audio_clips=audio_requests,
        subtitle_clips=subtitle_requests,
        meta={"generation_id": generation_id, "skipped": skipped},
    )

    def _on_progress(percent: int, stage: str) -> None:
        _persist_progress(factory, generation_id, percent, stage)
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_PROGRESS,
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={"shot_id": None, "progress": percent, "stage": stage},
            )
        )

    try:
        result = await provider.render(request, _on_progress)
    except Exception as exc:  # noqa: BLE001 — provider error
        logger.exception("render generation %s provider error", generation_id)
        _handle_failure(factory, generation_id, project_id, None, f"Provider error: {exc}", exc=exc)
        return

    if generation_id in _cancelled or _db_status(factory, generation_id) == "cancelling":
        _handle_cancelled(factory, generation_id, project_id, None)
        return
    if not result.success:
        _handle_failure(factory, generation_id, project_id, None, result.error or "Render failed.")
        return

    _persist_render_output(factory, generation_id, project_id, params, result)


def _persist_render_output(
    factory: Callable,
    generation_id: str,
    project_id: str,
    params: dict,
    result,
) -> None:
    """Register the rendered export as a FINAL_VIDEO asset in ONE transaction.

    - Asset: type video, copied into the project tree (AssetService).
    - Version group vg:episode:{episode_id}:FINAL_VIDEO (immutable V1/V2...).
    - Thumbnail: the renderer's frame-strip doubles as the poster.
    - timeline.status → RENDERED; timeline.rendered event.
    """
    from pathlib import Path as _Path

    from app.db.models import Asset, GenerationOutput, Timeline

    episode_id = params.get("episode_id") or ""
    timeline_id = params.get("timeline_id")

    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.status in ("cancelled", "cancelling") or generation_id in _cancelled:
            return
        if not result.output_path or not _Path(result.output_path).is_file():
            generation.error_message = "Render returned no output file."
            validate_transition(generation.status, "failed")
            generation.status = "failed"
            generation.completed_at = _now()
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_FAILED,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={"type": "render", "error": {"code": "GENERATION_FAILED", "message": "No output file."}},
                )
            )
            return

        asset_svc = AssetService(session)
        asset = asset_svc.register_asset(
            project_id=project_id,
            asset_type="video",
            source_path=result.output_path,
            name=None,
            shot_id=None,
            generation_id=generation_id,
            meta={
                "provider": generation.provider,
                "render": result.extra or {},
                "timeline_id": timeline_id,
            },
            make_thumbnail=False,
            commit=False,
        )
        session.flush()  # materialize asset.id before generation_outputs references it

        # FINAL_VIDEO immutable version group
        from app.services.render_service import final_video_version_group

        group = final_video_version_group(episode_id)
        current = session.scalar(
            select(func.max(Asset.version_number)).where(
                Asset.version_group_id == group, Asset.deleted_at.is_(None)
            )
        )
        asset.version_group_id = group
        asset.version_number = (current or 0) + 1
        asset.duration = result.duration
        extra = result.extra or {}
        asset.width = extra.get("width")
        asset.height = extra.get("height")
        name = asset.name or ""
        if name.lower().endswith(".mp4"):
            asset.mime_type = "video/mp4"
        elif name.lower().endswith(".avi"):
            asset.mime_type = "video/x-msvideo"
        else:
            asset.mime_type = "video/mp4"

        # poster = renderer frame-strip (preview image) stored next to the file
        strip = extra.get("frame_strip_path")
        if strip and _Path(strip).is_file():
            try:
                thumb_name = (asset.name or "video").rsplit(".", 1)[0] + "_thumb.jpg"
                from app.services.asset_service import project_dir as _proj_dir

                dest_dir = _proj_dir(project_id) / "video"
                dest_dir.mkdir(parents=True, exist_ok=True)
                thumb_dest = dest_dir / thumb_name
                thumb_dest.write_bytes(_Path(strip).read_bytes())
                asset.thumbnail_path = "video/" + thumb_name
            except Exception as exc:  # noqa: BLE001 — poster is best-effort
                logger.warning("render poster copy failed: %s", exc)

        session.add(
            GenerationOutput(
                generation_id=generation_id,
                asset_id=asset.id,
                role="primary",
                order_index=1000,
            )
        )

        timeline: Timeline | None = None
        if timeline_id:
            timeline = session.get(Timeline, timeline_id)
            if timeline is not None and timeline.project_id == project_id:
                timeline.status = "RENDERED"
                from app.db.models.columns import utcnow_iso

                timeline.updated_at = utcnow_iso()

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
                payload={"type": "video", "role": "FINAL_VIDEO", "episode_id": episode_id},
            )
        )
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_COMPLETED,
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={
                    "shot_id": None,
                    "type": "render",
                    "asset_id": asset.id,
                    "version_number": asset.version_number,
                    "episode_id": episode_id,
                },
            )
        )
        if timeline is not None:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_TIMELINE_RENDERED,
                    entity_type="timeline",
                    entity_id=timeline.id,
                    project_id=project_id,
                    payload={
                        "episode_id": episode_id,
                        "output_asset_id": asset.id,
                        "version_number": asset.version_number,
                        "duration": asset.duration,
                    },
                )
            )
        logger.info(
            "render generation %s completed -> FINAL_VIDEO V%d (episode %s)",
            generation_id, asset.version_number, episode_id,
        )


# ------------------------------------------------------------------ TASK-012 voiceover


async def _run_audio_generation(
    factory: Callable,
    generation_id: str,
    project_id: str,
    provider_id: str,
    params: dict,
) -> None:
    """Execute a type='audio' generation: synthesize through the AudioProvider,
    persist the AUDIO asset + clip re-bind on success (shared failure routing)."""
    provider = get_audio_provider(provider_id)

    request = AudioRequest(
        text=params.get("text", ""),
        voice=params.get("voice"),
        rate=params.get("rate"),
        metadata={"generation_id": generation_id, "timeline_clip_id": params.get("timeline_clip_id")},
    )

    def _on_progress(percent: int, stage: str) -> None:
        _persist_progress(factory, generation_id, percent, stage)
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_PROGRESS,
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={
                    "shot_id": None,
                    "type": "audio",
                    "progress": percent,
                    "stage": stage,
                },
            )
        )

    try:
        result = await provider.synthesize(request, _on_progress)
    except Exception as exc:  # noqa: BLE001 — provider error
        logger.exception("voiceover generation %s provider error", generation_id)
        _handle_failure(factory, generation_id, project_id, None, f"Provider error: {exc}", exc=exc)
        return

    if generation_id in _cancelled or _db_status(factory, generation_id) == "cancelling":
        _handle_cancelled(factory, generation_id, project_id, None)
        return
    if not result.success:
        _handle_failure(factory, generation_id, project_id, None, result.error or "Voiceover failed.")
        return

    _persist_voiceover_output(factory, generation_id, project_id, params, result)


def _persist_voiceover_output(
    factory: Callable,
    generation_id: str,
    project_id: str,
    params: dict,
    result,
) -> None:
    """Register the synthesized audio as an immutable AUDIO asset in ONE transaction.

    - Asset: type audio under vg:clip:{clip_id}:AUDIO (V1/V2... never overwrite).
    - The VOICE clip is re-bound to the newest asset (replace-asset semantics).
    """
    from pathlib import Path as _Path

    from app.db.models import TimelineClip
    from app.events.bus import EVENT_TIMELINE_CLIP_UPDATED
    from app.services.audio_service import clip_audio_version_group

    clip_id = params.get("timeline_clip_id")

    with factory() as session:
        generation = session.get(Generation, generation_id)
        if generation is None or generation.status in ("cancelled", "cancelling") or generation_id in _cancelled:
            return
        if not result.output_path or not _Path(result.output_path).is_file():
            validate_transition(generation.status, "failed")
            generation.status = "failed"
            generation.error_message = "Voiceover returned no output file."
            generation.completed_at = _now()
            session.commit()
            bus.publish(
                StudioEvent(
                    event_type=EVENT_GENERATION_FAILED,
                    entity_type="generation",
                    entity_id=generation_id,
                    project_id=project_id,
                    payload={"type": "audio", "error": {"code": "GENERATION_FAILED", "message": "No output file."}},
                )
            )
            return

        asset_svc = AssetService(session)
        asset = asset_svc.register_asset(
            project_id=project_id,
            asset_type="audio",
            source_path=result.output_path,
            shot_id=None,
            generation_id=generation_id,
            meta={
                "provider": generation.provider,
                "voice": (result.extra or {}).get("voice") or params.get("voice"),
                "role": "VOICEOVER",
                "timeline_clip_id": clip_id,
                "text_head": (params.get("text") or "")[:120],
            },
            make_thumbnail=False,
            commit=False,  # caller-owned transaction
        )
        session.flush()  # materialize asset.id before version group / outputs reference it

        name = asset.name.lower()
        asset.mime_type = "audio/wav" if name.endswith(".wav") else "audio/mpeg"
        asset.duration = result.duration

        # Immutable VOICEOVER version group (mirrors FINAL_VIDEO numbering).
        from app.db.models import Asset

        group = clip_audio_version_group(clip_id or "")
        current = session.scalar(
            select(func.max(Asset.version_number)).where(
                Asset.version_group_id == group, Asset.deleted_at.is_(None)
            )
        )
        asset.version_group_id = group
        asset.version_number = (current or 0) + 1

        session.add(
            GenerationOutput(
                generation_id=generation_id,
                asset_id=asset.id,
                role="primary",
                order_index=1000,
            )
        )

        # Re-bind the VOICE clip to the newest synthesis (replace-asset semantics).
        timeline_id = params.get("timeline_id")
        clip: TimelineClip | None = session.get(TimelineClip, clip_id) if clip_id else None
        if clip is not None and clip.asset_id != asset.id:
            clip.asset_id = asset.id

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
                payload={"type": "audio", "role": "VOICEOVER", "timeline_clip_id": clip_id},
            )
        )
        bus.publish(
            StudioEvent(
                event_type=EVENT_GENERATION_COMPLETED,
                entity_type="generation",
                entity_id=generation_id,
                project_id=project_id,
                payload={
                    "shot_id": None,
                    "type": "audio",
                    "asset_id": asset.id,
                    "version_number": asset.version_number,
                    "timeline_clip_id": clip_id,
                },
            )
        )
        if clip is not None:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_TIMELINE_CLIP_UPDATED,
                    entity_type="timeline_clip",
                    entity_id=clip.id,
                    project_id=project_id,
                    payload={"timeline_id": timeline_id, "track_id": clip.track_id, "event": "updated"},
                )
            )
        logger.info(
            "voiceover generation %s completed -> AUDIO V%d (clip %s)",
            generation_id, asset.version_number, clip_id,
        )
