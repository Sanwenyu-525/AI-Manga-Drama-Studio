"""Internal Event Bus (api-event-contract §109-111).

Stage A: services publish domain events AFTER committing the DB transaction
(red line: commit first, publish second — never the reverse).
Subscribers (WebSocket gateway, workflow listeners, agent listeners) plug in later stages.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger("events")

Subscriber = Callable[["StudioEvent"], None]

# Event names (api-event-contract §55-70) — Stage A/C subset.
EVENT_SHOT_UPDATED = "shot.updated"
EVENT_SHOT_CREATED = "shot.created"
EVENT_SHOT_DELETED = "shot.deleted"
EVENT_SHOT_RESTORED = "shot.restored"  # P2-E2-T01: lifecycle restore
EVENT_SHOT_ACTIVE_VERSION_CHANGED = "shot.active_version.changed"
EVENT_CHARACTER_CREATED = "character.created"
EVENT_CHARACTER_UPDATED = "character.updated"
EVENT_CHARACTER_DELETED = "character.deleted"
EVENT_CHARACTER_RESTORED = "character.restored"  # P2-E2-T01
EVENT_CHARACTER_VERSION_CREATED = "character.version.created"
EVENT_CHARACTER_VERSION_ACTIVATED = "character.version.activated"
EVENT_LOCATION_CREATED = "location.created"
EVENT_LOCATION_UPDATED = "location.updated"
EVENT_LOCATION_DELETED = "location.deleted"
EVENT_LOCATION_VERSION_CREATED = "location.version.created"
EVENT_LOCATION_VERSION_ACTIVATED = "location.version.activated"
EVENT_COSTUME_CREATED = "costume.created"
EVENT_COSTUME_UPDATED = "costume.updated"
EVENT_COSTUME_DELETED = "costume.deleted"
EVENT_DOCUMENT_CREATED = "document.created"
EVENT_DOCUMENT_UPDATED = "document.updated"
EVENT_DOCUMENT_DELETED = "document.deleted"
EVENT_SCENE_CREATED = "scene.created"
EVENT_SCENE_UPDATED = "scene.updated"
EVENT_SCENE_DELETED = "scene.deleted"
EVENT_SCENE_RESTORED = "scene.restored"  # P2-E2-T01
EVENT_EPISODE_CREATED = "episode.created"
EVENT_EPISODE_UPDATED = "episode.updated"
EVENT_EPISODE_DELETED = "episode.deleted"
EVENT_EPISODE_RESTORED = "episode.restored"  # P2-E2-T01
EVENT_PROJECT_CREATED = "project.created"
EVENT_PROJECT_UPDATED = "project.updated"
EVENT_PROJECT_DELETED = "project.deleted"
EVENT_PROJECT_RESTORED = "project.restored"  # P2-E2-T01

EVENT_ASSET_CREATED = "asset.created"
EVENT_ASSET_ARCHIVED = "asset.archived"  # P2-E2-T02: archive (soft delete)
EVENT_ASSET_RESTORED = "asset.restored"  # P2-E2-T02: restore from archive
EVENT_ASSET_DELETED = "asset.deleted"  # P2-E2-T02: physical delete (irreversible)

EVENT_GENERATION_CREATED = "generation.created"
EVENT_GENERATION_QUEUED = "generation.queued"
EVENT_GENERATION_STARTED = "generation.started"
EVENT_GENERATION_PROGRESS = "generation.progress"
EVENT_GENERATION_COMPLETED = "generation.completed"
EVENT_GENERATION_FAILED = "generation.failed"
EVENT_GENERATION_CANCELLED = "generation.cancelled"
EVENT_GENERATION_RETRYING = "generation.retrying"
EVENT_GENERATION_INTERRUPTED = "generation.interrupted"  # P5-T016

EVENT_PROVIDER_CONNECTED = "provider.connected"
EVENT_PROVIDER_DISCONNECTED = "provider.disconnected"
EVENT_LLM_FALLBACK_USED = "llm.fallback.used"  # P-LLM-Fallback：降级大声宣告（不静默掩盖）

EVENT_AGENT_RUN_STARTED = "agent.run.started"
EVENT_AGENT_INTENT_RESOLVED = "agent.intent.resolved"
EVENT_AGENT_CONTEXT_LOADED = "agent.context.loaded"
EVENT_AGENT_PLAN_CREATED = "agent.plan.created"
EVENT_AGENT_APPROVAL_REQUIRED = "agent.approval.required"
EVENT_AGENT_RESUMED = "agent.resumed"
EVENT_AGENT_TOOL_STARTED = "agent.tool.started"
EVENT_AGENT_TOOL_COMPLETED = "agent.tool.completed"
EVENT_AGENT_REVIEW_STARTED = "agent.review.started"
EVENT_AGENT_REVIEW_COMPLETED = "agent.review.completed"
EVENT_AGENT_CHANGE_SET_CREATED = "agent.change_set.created"
EVENT_AGENT_RUN_COMPLETED = "agent.run.completed"
EVENT_AGENT_RUN_FAILED = "agent.run.failed"
EVENT_AGENT_RUN_CANCELLED = "agent.run.cancelled"
EVENT_AGENT_RUN_AWAITING_APPROVAL = "agent.run.awaiting_approval"
# C 真流式：graph 节点内的阶段增量（状态文本分片，非 LLM token 冒充——structured
# planner 本就没有 token 流）。前端拼成打字机 + 思考时间线。
EVENT_AGENT_RUN_STREAM = "agent.run.stream"
# P7-T012/13/15/16: proposal lifecycle events.
EVENT_AGENT_PROPOSAL_CREATED = "agent.proposal.created"
EVENT_AGENT_PROPOSAL_APPROVED = "agent.proposal.approved"
EVENT_AGENT_PROPOSAL_REJECTED = "agent.proposal.rejected"
EVENT_AGENT_PROPOSAL_CONFLICT = "agent.proposal.conflict"
EVENT_AGENT_PROPOSAL_EXPIRED = "agent.proposal.expired"  # P2-E3-T02: TTL elapsed
# P2-E3-T03: change set lifecycle (undo = compensating change, history untouched).
EVENT_AGENT_CHANGE_SET_UNDONE = "agent.change_set.undone"
# P8-T018/T019: continuity warning lifecycle events.
EVENT_CONTINUITY_WARNING_CREATED = "continuity.warning.created"
EVENT_CONTINUITY_WARNING_ACKNOWLEDGED = "continuity.warning.acknowledged"
EVENT_CONTINUITY_WARNING_FIXED = "continuity.warning.fixed"
# P5-E2: job / task events (api-event-contract §143)
EVENT_JOB_CREATED = "job.created"
EVENT_JOB_UPDATED = "job.updated"
EVENT_JOB_COMPLETED = "job.completed"
EVENT_JOB_FAILED = "job.failed"
EVENT_JOB_CANCELLED = "job.cancelled"
EVENT_JOB_PAUSED = "job.paused"
EVENT_JOB_RESUMED = "job.resumed"
EVENT_JOB_TASK_UPDATED = "job.task.updated"
# P9: timeline + episode render events (api-event-contract §93.4)
EVENT_TIMELINE_CREATED = "timeline.created"
EVENT_TIMELINE_UPDATED = "timeline.updated"
EVENT_TIMELINE_TRACK_UPDATED = "timeline.track.updated"
EVENT_TIMELINE_CLIP_CREATED = "timeline.clip.created"
EVENT_TIMELINE_CLIP_UPDATED = "timeline.clip.updated"
EVENT_TIMELINE_CLIP_DELETED = "timeline.clip.deleted"
EVENT_TIMELINE_RENDERED = "timeline.rendered"
EVENT_TIMELINE_RENDER_FAILED = "timeline.render.failed"



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
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._wildcards: list[Subscriber] = []
        self._sequence = 0

    def subscribe(self, event_type: str, callback: Subscriber) -> None:
        if event_type == "*":
            self._wildcards.append(callback)
        else:
            self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Subscriber) -> None:
        """Remove a previous subscription (P1-E4-T02: explicit subscription handle —
        repeated app lifespans must not accumulate duplicate gateway subscribers)."""
        if event_type == "*":
            try:
                self._wildcards.remove(callback)
            except ValueError:
                pass
            return
        subscribers = self._subscribers.get(event_type)
        if subscribers is not None:
            try:
                subscribers.remove(callback)
            except ValueError:
                pass

    def subscriber_count(self, event_type: str = "*") -> int:
        """Diagnostic helper (tests/health): number of subscribers for a type."""
        if event_type == "*":
            return len(self._wildcards)
        return len(self._subscribers.get(event_type, []))

    def publish(self, event: StudioEvent) -> None:
        self._sequence += 1
        logger.info(
            "event published: type=%s entity=%s/%s",
            event.event_type,
            event.entity_type,
            event.entity_id,
        )
        callbacks = list(self._subscribers.get(event.event_type, [])) + list(self._wildcards)
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("event subscriber failed for %s", event.event_type)


bus = EventBus()
