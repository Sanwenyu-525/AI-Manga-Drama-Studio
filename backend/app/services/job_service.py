"""JobService (P5-E1/E2, api-event-contract §142).

- create_scene_job: one SCENE_IMAGE job per scene; a 'image' JobTask per live shot,
  priority = shot_order. MVP creates NO task_dependencies (the DAG machinery is
  available + tested but scene jobs are dependency-free fan-out).
- get / list / pause / resume / cancel / retry control operations.
- DAG Validator (validate_dependencies): cycle + unknown-reference detection → 422.

Scheduling lives in app/jobs/scheduler.py (DB-poll loop). The Service only mutates on
explicit control actions; it never writes generation-level state (red line).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import Episode, Job, JobTask, Scene, Shot
from app.domain.job import JobRead, JobSummaryRead, JobTaskRead
from app.events.bus import (
    EVENT_JOB_CANCELLED,
    EVENT_JOB_CREATED,
    EVENT_JOB_PAUSED,
    EVENT_JOB_RESUMED,
    EVENT_JOB_UPDATED,
    StudioEvent,
    bus,
)
from app.jobs import state as job_state

logger = get_logger("jobs.service")

# tunable MVP knobs
JOB_TYPE_SCENE_IMAGE = "SCENE_IMAGE"
TASK_TERMINAL = job_state.TASK_TERMINAL


class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------- creation ----------

    def create_scene_job(self, scene_id: str, name: str | None) -> Job:
        """Create a SCENE_IMAGE job with one 'image' task per live shot (priority=shot_order).

        No task_dependencies in MVP (fan-out); DAG structure is validated separately.
        Commits + publishes job.created.
        """
        scene = self.session.get(Scene, scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        project_id = self._project_id_of(scene)
        if project_id is None:
            raise NotFoundError("Scene has no project.", {"scene_id": scene_id})

        # one image task per live shot, ordered by shot_order
        shots = list(
            self.session.scalars(
                select(Shot)
                .where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
                .order_by(Shot.shot_order, Shot.shot_number)
            )
        )

        job = Job(
            project_id=project_id,
            name=name or f"Scene {scene.scene_number} images",
            job_type=JOB_TYPE_SCENE_IMAGE,
            scene_id=scene_id,
            status="queued",
            progress=0,
        )
        self.session.add(job)
        self.session.flush()  # assign job.id before tasks reference it

        for shot in shots:
            self.session.add(
                JobTask(
                    job_id=job.id,
                    task_type="image",
                    target_type="shot",
                    target_id=shot.id,
                    status="queued",
                    priority=shot.shot_order or 0,
                    progress=0,
                )
            )
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_JOB_CREATED,
                entity_type="job",
                entity_id=job.id,
                project_id=project_id,
                payload={"job_type": job.job_type, "scene_id": scene_id, "task_count": len(shots)},
            )
        )
        logger.info("job %s created for scene %s (%d image tasks)", job.id, scene_id, len(shots))
        return job

    # ---------- DAG validator (P5-E1) ----------

    def validate_dependencies(
        self,
        task_ids: list[str],
        dependency_pairs: list[tuple[str, str]],
    ) -> None:
        """Validate a set of task ids + (task_id, depends_on_task_id) edges.

        - Every referenced id must be in task_ids (no unknown refs) → 422.
        - The directed graph must be acyclic (DFS) → 422 on cycle.
        Raises ValidationError (422) on any violation; returns None when valid.
        """
        known = set(task_ids)
        for task_id, dep_id in dependency_pairs:
            if task_id not in known or dep_id not in known:
                unknown = [x for x in (task_id, dep_id) if x not in known]
                raise ValidationError(
                    "Dependency references an unknown task id.",
                    {"unknown": unknown, "known": sorted(known)},
                )
        # adjacency: task -> deps
        adjacency: dict[str, list[str]] = {t: [] for t in task_ids}
        for task_id, dep_id in dependency_pairs:
            adjacency[task_id].append(dep_id)
        # DFS cycle detection (task -> its deps)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {t: WHITE for t in task_ids}

        def _dfs(node: str, stack: list[str]) -> None:
            color[node] = GRAY
            stack.append(node)
            for dep in adjacency.get(node, []):
                if color.get(dep, WHITE) == GRAY:
                    cycle_start = stack.index(dep) if dep in stack else 0
                    raise ValidationError(
                        "Dependency graph contains a cycle.",
                        {"cycle": stack[cycle_start:] + [dep]},
                    )
                if color.get(dep, WHITE) == WHITE:
                    _dfs(dep, stack)
            stack.pop()
            color[node] = BLACK

        for t in task_ids:
            if color[t] == WHITE:
                _dfs(t, [])

    # ---------- reads ----------

    def get_job(self, job_id: str) -> JobRead:
        job = self.session.get(Job, job_id)
        if job is None:
            raise NotFoundError("Job does not exist.", {"job_id": job_id})
        tasks = self._load_tasks(job_id)
        return self._to_read(job, tasks)

    def list_jobs(self, project_id: str) -> list[JobSummaryRead]:
        jobs = list(
            self.session.scalars(
                select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc())
            )
        )
        summaries: list[JobSummaryRead] = []
        for job in jobs:
            tasks = self._load_tasks(job.id)
            counts = self._status_counts(tasks)
            summaries.append(
                JobSummaryRead(
                    id=job.id,
                    project_id=job.project_id,
                    name=job.name,
                    job_type=job.job_type,
                    scene_id=job.scene_id,
                    status=job.status,
                    progress=job.progress,
                    error_summary=job.error_summary,
                    task_count=counts["total"],
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )
        return summaries

    # ---------- control ----------

    def pause_job(self, job_id: str) -> JobRead:
        job = self._get(job_id)
        state = job.status
        if state in ("completed", "failed", "cancelled"):
            job_state.validate_job_transition(state, "paused")  # raises ConflictError
        job_state.validate_job_transition(state, "paused")
        job.status = "paused"
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_JOB_PAUSED,
                entity_type="job",
                entity_id=job.id,
                project_id=job.project_id,
                payload={"previous_status": state},
            )
        )
        return self.get_job(job_id)

    def resume_job(self, job_id: str) -> JobRead:
        job = self._get(job_id)
        job_state.validate_job_transition(job.status, "queued")
        job.status = "queued"
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_JOB_RESUMED,
                entity_type="job",
                entity_id=job.id,
                project_id=job.project_id,
            )
        )
        return self.get_job(job_id)

    def cancel_job(self, job_id: str) -> JobRead:
        """Cancel a job: unfinished tasks → cancelled; running generations go through the
        existing GenerationService.cancel path + worker interrupt.
        """
        job = self._get(job_id)
        if job.status in ("completed", "cancelled"):
            job_state.validate_job_transition(job.status, "cancelled")  # raises ConflictError
        job_state.validate_job_transition(job.status, "cancelled")
        job_id = str(job.id)
        tasks = self._load_tasks(job_id)
        running_gen_ids: list[str] = []
        for task in tasks:
            if task.status in job_state.TASK_TERMINAL:
                continue
            if task.generation_id:
                running_gen_ids.append(task.generation_id)
            job_state.validate_task_transition(task.status, "cancelled")
            task.status = "cancelled"
            self.session.add(task)
        cancelled_tasks = sum(1 for t in tasks if t.status == "cancelled")
        job.status = "cancelled"
        job.progress = self._progress_percent(tasks)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_JOB_CANCELLED,
                entity_type="job",
                entity_id=job.id,
                project_id=job.project_id,
                payload={"cancelled_tasks": cancelled_tasks},
            )
        )
        logger.info("job %s cancelled (%d tasks, %d running generations)", job_id, cancelled_tasks, len(running_gen_ids))
        return self.get_job(job_id), running_gen_ids

    def retry_job(self, job_id: str) -> JobRead:
        """Job-level retry: re-queue non-success terminal tasks (failed/dependency_failed/
        skipped/cancelled), clear their generation refs, and reopen the job to 'queued'.
        Completed tasks stay completed. Re-drives via the scheduler."""
        job = self._get(job_id)
        if job.status in ("queued", "running", "paused", "created"):
            job_state.validate_job_transition(job.status, "queued")
        job_state.validate_job_transition(job.status, "queued")
        tasks = self._load_tasks(job_id)
        reopened = 0
        for task in tasks:
            if task.status in ("failed", "dependency_failed", "skipped", "cancelled"):
                job_state.validate_task_transition(task.status, "queued")
                task.status = "queued"
                task.progress = 0
                task.generation_id = None
                task.error_message = None
                self.session.add(task)
                reopened += 1
        job.status = "queued"
        job.error_summary = None
        job.progress = self._progress_percent(tasks)
        self.session.commit()
        if reopened:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_JOB_UPDATED,
                    entity_type="job",
                    entity_id=job.id,
                    project_id=job.project_id,
                    payload={"status": "queued", "reopened_tasks": reopened},
                )
            )
        logger.info("job %s retried (%d tasks reopened)", job_id, reopened)
        return self.get_job(job_id)

    # ---------- helpers ----------

    def _get(self, job_id: str) -> Job:
        job = self.session.get(Job, job_id)
        if job is None:
            raise NotFoundError("Job does not exist.", {"job_id": job_id})
        return job

    def _load_tasks(self, job_id: str) -> list[JobTask]:
        return list(
            self.session.scalars(
                select(JobTask).where(JobTask.job_id == job_id).order_by(JobTask.priority, JobTask.created_at)
            )
        )

    @staticmethod
    def _status_counts(tasks: list[JobTask]) -> dict[str, int]:
        counts: dict[str, int] = {"total": len(tasks)}
        for task in tasks:
            counts[task.status] = counts.get(task.status, 0) + 1
        return counts

    @staticmethod
    def _progress_percent(tasks: list[JobTask]) -> int:
        if not tasks:
            return 0
        return round(sum(1 for t in tasks if t.status == "completed") / len(tasks) * 100)

    def _to_read(self, job: Job, tasks: list[JobTask]) -> JobRead:
        counts = self._status_counts(tasks)
        task_reads = [
            JobTaskRead(
                id=t.id,
                job_id=t.job_id,
                task_type=t.task_type,
                target_type=t.target_type,
                target_id=t.target_id,
                shot_id=t.target_id,
                status=t.status,
                priority=t.priority,
                progress=t.progress,
                generation_id=t.generation_id,
                error_message=t.error_message,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tasks
        ]
        return JobRead(
            id=job.id,
            project_id=job.project_id,
            name=job.name,
            job_type=job.job_type,
            scene_id=job.scene_id,
            status=job.status,
            progress=job.progress,
            error_summary=job.error_summary,
            created_at=job.created_at,
            updated_at=job.updated_at,
            task_count=counts["total"],
            task_status_counts=counts,
            tasks=task_reads,
        )

    def _project_id_of(self, scene: Scene) -> str | None:
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
