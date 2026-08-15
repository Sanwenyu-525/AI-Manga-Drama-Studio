"""JobScheduler (P5-E1/E2/E3/E4, roadmap §33-38): the DB-poll scheduler.

MIRRORS the generation worker's DB-poll style (generations/worker.py): the DB IS the
queue. A separate scheduler loop polls jobs (queued/running) and advances each job one
step; it NEVER runs a generation itself — it drives each job_task to the point of having
a generation (created via GenerationService) and then reflects the generation's terminal
status back onto the task. The existing generation worker actually executes generations.

Advance rules (one pass per call, idempotent):
- A task with unsatisfied dependencies or a job that is paused/completed/etc is skipped.
- No generation & deps satisfied  → GenerationService.create_generation('image') and link
                                   task.generation_id (duplicate-safe: link checked first).
- Has generation                 → map generation status → task status:
                                   completed → task completed(100) · failed/interrupted →
                                   failed(+error) · cancelled → cancelled · running →
                                   running(progress) · queued/retrying → queued.
- A task whose dependency reached a non-success terminal (failed/dependency_failed/
  skipped/cancelled) → dependency_failed (no new generation created).
- job.progress = round(completed/total*100); all tasks terminal → job completed
  (failed tasks aggregate into error_summary, and the job still ends 'completed' so the
  partial-failure contract holds: failure does not block siblings).

The scheduler can be started as its own asyncio task (scheduler_loop) alongside the
generation worker; tests drive advance_job directly for synchronous control.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import session as db_session_module
from app.db.models import Generation, Job, JobTask, TaskDependency
from app.domain.generation import GenerationCreate
from app.events.bus import (
    EVENT_JOB_COMPLETED,
    EVENT_JOB_TASK_UPDATED,
    EVENT_JOB_UPDATED,
    StudioEvent,
    bus,
)
from app.jobs import state as job_state
from app.services.generation_service import GenerationService

logger = get_logger("jobs.scheduler")

POLL_INTERVAL_SECONDS = 0.5

# whether the scheduler is active (used by the gate tests to avoid a background loop
# racing with direct advance_job calls).
_enabled = True

last_heartbeat: float = 0.0
SCHEDULER_STALE_SECONDS = 15.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


def set_enabled(value: bool) -> None:
    """Test hook: disable the background scheduler loop so direct advance_job calls are
    the only advancement source (avoids races in synchronous-drive tests)."""
    global _enabled
    _enabled = value


def is_enabled() -> bool:
    return _enabled


def _gen_map(session: Session, task: JobTask, generations: dict[str, Generation]) -> Generation | None:
    return generations.get(task.generation_id) if task.generation_id else None


def _load_deps(session: Session, task_ids: list[str]) -> dict[str, list[str]]:
    """task_id → list of depends_on_task_ids (fan-in edges)."""
    if not task_ids:
        return {}
    rows = session.scalars(
        select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
    )
    mapping: dict[str, list[str]] = {}
    for row in rows:
        mapping.setdefault(row.task_id, []).append(row.depends_on_task_id)
    return mapping


def advance_job(job_id: str, factory: Callable | None = None) -> str:
    """Advance one job one pass; returns the job's status after the pass.

    factory defaults to the app session factory (overridable for tests). Commit-then-
    publish for every event. Idempotent: repeated calls never duplicate generations.
    """
    f = factory or db_session_module.session_factory_provider()
    with f() as session:
        job = session.get(Job, job_id)
        if job is None or job.status not in ("queued", "running"):
            return job.status if job is not None else "missing"

        # entering scheduling → running (legal queued→running; running stays running)
        if job.status == "queued":
            job_state.validate_job_transition(job.status, "running")
            job.status = "running"

        tasks = list(
            session.scalars(
                select(JobTask).where(JobTask.job_id == job_id).order_by(JobTask.priority, JobTask.created_at)
            )
        )
        by_id = {t.id: t for t in tasks}
        deps = _load_deps(session, [t.id for t in tasks])

        # load referenced generations once
        gen_ids = {t.generation_id for t in tasks if t.generation_id}
        generations: dict[str, Generation] = {}
        if gen_ids:
            for g in session.scalars(select(Generation).where(Generation.id.in_(gen_ids))):
                generations[g.id] = g

        completed_count = 0
        failed_count = 0
        failed_msgs: list[str] = []
        changed: list[JobTask] = []

        for task in tasks:
            if task.status in job_state.TASK_TERMINAL:
                # non-success terminal still blocks downstream; completed counts progress
                if task.status == "completed":
                    completed_count += 1
                elif task.status in job_state.TASK_BLOCKED:
                    failed_count += 1
                    if task.error_message:
                        failed_msgs.append(task.error_message)
                continue

            # --- dependency gating ---
            dep_ids = deps.get(task.id, [])
            blocked_by: tuple[str, str] | None = None  # (dep_task_id, dep_status)
            waiting = False
            for dep_id in dep_ids:
                dep = by_id.get(dep_id)
                if dep is None:
                    continue
                if dep.status in job_state.TASK_BLOCKED:
                    blocked_by = (dep_id, dep.status)
                    break
                if dep.status not in ("completed",):
                    waiting = True
            if blocked_by is not None:
                job_state.validate_task_transition(task.status, "dependency_failed")
                task.status = "dependency_failed"
                task.error_message = (
                    f"Dependency task {blocked_by[0]} did not complete ({blocked_by[1]})."
                )
                failed_count += 1
                failed_msgs.append(task.error_message)
                changed.append(task)
                continue
            if waiting:
                continue  # wait for dependencies this round

            generation = _gen_map(session, task, generations)

            if generation is None:
                # create a generation for this task (deps satisfied). A deterministic
                # failure (missing prompt, unknown workflow) must fail THIS task without
                # aborting the whole pass (P5-E4 partial failure).
                try:
                    gen = GenerationService(session).create_generation(
                        task.target_id, GenerationCreate(type="image")
                    )
                except Exception as exc:  # noqa: BLE001 — task-level failure isolation
                    from app.core.errors import StudioError

                    if isinstance(exc, StudioError):
                        job_state.validate_task_transition(task.status, "failed")
                        task.status = "failed"
                        task.error_message = (str(exc.message) if exc.message else str(exc))[:2000]
                        failed_count += 1
                        failed_msgs.append(task.error_message)
                        changed.append(task)
                        continue
                    raise
                task.generation_id = gen.id
                # keep task queued (generation is queued); do not reset a running task
                changed.append(task)
                continue

            # --- reflect generation status ---
            gstatus = generation.status
            if gstatus == "completed":
                job_state.validate_task_transition(task.status, "completed")
                task.status = "completed"
                task.progress = 100
                completed_count += 1
            elif gstatus in ("failed", "interrupted"):
                job_state.validate_task_transition(task.status, "failed")
                task.status = "failed"
                task.error_message = (generation.error_message or "Generation failed.")[:2000]
                failed_count += 1
                failed_msgs.append(task.error_message)
            elif gstatus == "cancelled":
                job_state.validate_task_transition(task.status, "cancelled")
                task.status = "cancelled"
                task.error_message = "Generation was cancelled."
                failed_count += 1
                failed_msgs.append(task.error_message)
            elif gstatus == "running" and task.status != "running":
                job_state.validate_task_transition(task.status, "running")
                task.status = "running"
                task.progress = generation.progress or 0
                changed.append(task)
            elif gstatus in ("running", "queued", "retrying", "cancelling", "created"):
                task.progress = generation.progress or 0
            changed.append(task)

        # — persistence + events —
        total = len(tasks) or 1
        # progress = share of COMPLETED tasks (a task that failed or is cancelled does
        # not add to progress; it does add to the denominator so partial failure lowers it).
        job.progress = round(completed_count / total * 100)
        job.updated_at = _now()
        all_terminal = all(t.status in job_state.TASK_TERMINAL for t in tasks)

        if all_terminal:
            job_state.validate_job_transition(job.status, "completed")
            job.status = "completed"
            if failed_count:
                job.error_summary = (
                    f"{failed_count} task(s) did not complete. "
                    + "; ".join(failed_msgs[:5])
                )[:2000]
            else:
                job.error_summary = None

        session.commit()

        # publish after commit (red line)
        for task in changed:
            if task.generation_id:
                bus.publish(
                    StudioEvent(
                        event_type=EVENT_JOB_TASK_UPDATED,
                        entity_type="job_task",
                        entity_id=task.id,
                        project_id=job.project_id,
                        payload={
                            "task_id": task.id,
                            "task_type": task.task_type,
                            "shot_id": task.target_id,
                            "status": task.status,
                            "generation_id": task.generation_id,
                        },
                    )
                )
        if all_terminal:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_JOB_COMPLETED,
                    entity_type="job",
                    entity_id=job.id,
                    project_id=job.project_id,
                    payload={
                        "status": job.status,
                        "progress": job.progress,
                        "failed_count": failed_count,
                        "error_summary": job.error_summary,
                    },
                )
            )
        else:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_JOB_UPDATED,
                    entity_type="job",
                    entity_id=job.id,
                    project_id=job.project_id,
                    payload={"status": job.status, "progress": job.progress},
                )
            )
        return job.status


async def scheduler_loop() -> None:
    """Poll DB for schedulable jobs (queued/running) and advance them serially."""
    global last_heartbeat
    last_heartbeat = time.monotonic()
    logger.info("job scheduler started (db poll)")
    while True:
        last_heartbeat = time.monotonic()
        try:
            if not _enabled:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            factory = db_session_module.session_factory_provider()
            with factory() as session:
                job_ids = list(
                    session.scalars(
                        select(Job.id).where(Job.status.in_(("queued", "running")))
                    )
                )
            for job_id in job_ids:
                advance_job(job_id, factory)
        except Exception:  # noqa: BLE001 — scheduler must never die
            logger.exception("job scheduler poll iteration failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
