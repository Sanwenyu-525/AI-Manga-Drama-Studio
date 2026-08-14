"""Internal Event Bus (api-event-contract §109-111).

Stage A: services publish domain events AFTER committing the DB transaction
(red line: commit first, publish second — never the reverse).
Subscribers (WebSocket gateway, workflow listeners, agent listeners) plug in later stages.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.logging import get_logger

logger = get_logger("events")

Subscriber = Callable[["StudioEvent"], None]

# Event names (api-event-contract §55-70) — Stage A subset.
EVENT_SHOT_UPDATED = "shot.updated"
EVENT_SHOT_CREATED = "shot.created"
EVENT_SHOT_DELETED = "shot.deleted"
EVENT_SCENE_CREATED = "scene.created"
EVENT_SCENE_UPDATED = "scene.updated"
EVENT_PROJECT_CREATED = "project.created"
EVENT_PROJECT_UPDATED = "project.updated"


@dataclass
class StudioEvent:
    """Studio domain event envelope — never leak LangGraph / ComfyUI formats (contract §112-115)."""

    event_type: str
    entity_type: str
    entity_id: str
    project_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._sequence = 0

    def subscribe(self, event_type: str, callback: Subscriber) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def publish(self, event: StudioEvent) -> None:
        self._sequence += 1
        logger.info(
            "event published: type=%s entity=%s/%s",
            event.event_type,
            event.entity_type,
            event.entity_id,
        )
        for callback in self._subscribers.get(event.event_type, []):
            try:
                callback(event)
            except Exception:  # noqa: BLE001 — subscriber failure must not break the transaction
                logger.exception("event subscriber failed for %s", event.event_type)


bus = EventBus()
