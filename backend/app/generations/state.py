"""Generation state machine (P1-E2-T02): every status change goes through the table.

A transition that is not in ALLOWED_TRANSITIONS raises ConflictError (a Domain
Error) — no code path may write an arbitrary status directly. The DB-poll worker
claims rows with an atomic conditional UPDATE (see worker.py), so the table and
the claim together define the only legal status flow.
"""

from __future__ import annotations

from app.core.errors import ConflictError

# Statuses persisted in MVP (waiting_provider/processing_output exist in the
# contract but are not materialized as rows).
GENERATION_STATUSES = (
    "created",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "retrying",
    # P5-T016: abnormal-task detection — a running row whose lease expired and whose
    # attempt budget is exhausted becomes 'interrupted' (system interruption, not a
    # user failure).
    "interrupted",
    # P5-T015: a running row the user cancelled is flagged 'cancelling' (durable), so
    # the cancel survives a restart; the worker finalizes it to 'cancelled'.
    "cancelling",
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"queued"}),
    "queued": frozenset({"running", "cancelled"}),
    # running → queued happens ONLY through lease-expiry recovery (crash).
    "running": frozenset(
        {"completed", "failed", "cancelled", "retrying", "queued", "interrupted", "cancelling"}
    ),
    "retrying": frozenset({"running", "cancelled", "failed"}),
    # A cancelling row is finalized by the worker; it never resumes or retries.
    "cancelling": frozenset({"cancelled", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
}

TERMINAL = ("completed", "failed", "cancelled", "interrupted")


def validate_transition(current: str, new: str) -> None:
    """Raise ConflictError when the transition is not allowed (P1-E2-T02)."""
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ConflictError(
            f"Invalid generation state transition: {current} -> {new}.",
            {"current": current, "requested": new},
        )
