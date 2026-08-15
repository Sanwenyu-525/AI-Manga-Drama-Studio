"""Job / JobTask state machines (P5-E1/E2).

Every job / task status change goes through validate_transition (mirrors generations/state.py).
A transition not in the table raises ConflictError — no code path writes a raw status.

Job:     created|queued|running|paused|completed|failed|cancelled
Task:    queued|running|completed|failed|skipped|dependency_failed|cancelled

Job-level retry reopens non-success terminal states (failed/dependency_failed/skipped/
cancelled) back to queued so the scheduler re-drives them; completed tasks stay completed.
"""

from __future__ import annotations

from app.core.errors import ConflictError

JOB_STATUSES = (
    "created", "queued", "running", "paused", "completed", "failed", "cancelled",
)
JOB_TASK_STATUSES = (
    "queued", "running", "completed", "failed", "skipped", "dependency_failed", "cancelled",
)

JOB_ALLOWED: dict[str, frozenset] = {
    "created": frozenset({"queued"}),
    "queued": frozenset({"running", "paused", "cancelled"}),
    "running": frozenset({"paused", "cancelled", "completed", "failed"}),
    "paused": frozenset({"queued", "cancelled"}),
    "completed": frozenset({"queued"}),  # retry reopens a job that had failures
    "failed": frozenset({"queued"}),      # retry
    "cancelled": frozenset(),
}

JOB_TASK_ALLOWED: dict[str, frozenset] = {
    "queued": frozenset({"running", "completed", "failed", "cancelled", "dependency_failed", "skipped"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    # retry / reopen: non-success terminal states go back to queued
    "completed": frozenset({"queued"}),  # job retry may reopen a completed task (undone)
    "failed": frozenset({"queued"}),
    "dependency_failed": frozenset({"queued"}),
    "skipped": frozenset({"queued"}),
    "cancelled": frozenset({"queued"}),
}

JOB_TERMINAL = ("completed", "failed", "cancelled")
TASK_TERMINAL = ("completed", "failed", "skipped", "dependency_failed", "cancelled")
# task statuses that mean "this task will not produce output" (block downstream)
TASK_BLOCKED = ("failed", "skipped", "dependency_failed", "cancelled")


def validate_job_transition(current: str, new: str) -> None:
    allowed = JOB_ALLOWED.get(current, frozenset())
    if new not in allowed:
        raise ConflictError(
            f"Invalid job state transition: {current} -> {new}.",
            {"current": current, "requested": new},
        )


def validate_task_transition(current: str, new: str) -> None:
    allowed = JOB_TASK_ALLOWED.get(current, frozenset())
    if new not in allowed:
        raise ConflictError(
            f"Invalid job task state transition: {current} -> {new}.",
            {"current": current, "requested": new},
        )
