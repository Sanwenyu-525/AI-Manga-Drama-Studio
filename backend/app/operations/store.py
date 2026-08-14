"""Operation mechanism (api-event-contract §81-82, §15).

Operations are short background jobs (episode analysis, scene planning, prompt generation)
that return 202 + operation_id immediately and expose status via GET /operations/{id}.

Stage B keeps the store in-process (no DB table): operations are short-lived and
re-running is cheap. Generation (Stage C) gets its own persisted model.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.errors import NotFoundError
from app.core.logging import get_logger

logger = get_logger("operations")

OPERATION_STATUSES = ("queued", "running", "completed", "failed")

Job = Callable[[], Awaitable[Any]]


class OperationStore:
    """In-memory operation store with task tracking."""

    def __init__(self) -> None:
        self._operations: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def create(self, op_type: str, project_id: str | None = None) -> dict[str, Any]:
        op_id = f"op_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        op = {
            "id": op_id,
            "type": op_type,
            "project_id": project_id,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }
        self._operations[op_id] = op
        return op

    def start(self, op_id: str, job: Job) -> None:
        op = self._operations.get(op_id)
        if op is None:
            return
        op["status"] = "running"
        op["started_at"] = datetime.now(timezone.utc).isoformat()
        asyncio.create_task(self._run(op_id, job))

    async def _run(self, op_id: str, job: Job) -> None:
        op = self._operations.get(op_id)
        try:
            result = await job()
            op["result"] = result
            op["status"] = "completed"
        except Exception as exc:  # noqa: BLE001 — operation failure is reported via API, not raised
            logger.exception("operation %s failed", op_id)
            op["error"] = str(exc)
            op["status"] = "failed"
        finally:
            op["completed_at"] = datetime.now(timezone.utc).isoformat()

    def get(self, op_id: str) -> dict[str, Any]:
        op = self._operations.get(op_id)
        if op is None:
            raise NotFoundError("Operation does not exist.", {"operation_id": op_id})
        return op

    def lock_for(self, key: str) -> asyncio.Lock:
        """Per-key lock so the same episode/scene cannot run two analysis jobs at once."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]


operation_store = OperationStore()
