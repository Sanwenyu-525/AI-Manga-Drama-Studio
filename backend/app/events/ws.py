"""WebSocket event gateway (api-event-contract §49-53): /api/v1/events.

EventBus → WS: every Studio event is broadcast with the standard envelope
(event_id, event_type, event_version, project_id, entity_type, entity_id,
timestamp, sequence, payload). Clients use sequence to dedupe after reconnect.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.events.bus import StudioEvent, bus

logger = get_logger("events.ws")

router = APIRouter(tags=["events"])

_connections: set[WebSocket] = set()
_broadcast_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


def _envelope(event: StudioEvent, sequence: int) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_version": event.event_version,
        "project_id": event.project_id,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "timestamp": event.timestamp,
        "sequence": sequence,
        "payload": event.payload,
    }


def _on_event(event: StudioEvent) -> None:
    """EventBus subscriber → broadcast queue (never blocks the publisher)."""
    _broadcast_queue.put_nowait(_envelope(event, _next_sequence()))


_sequence = 0


def _next_sequence() -> int:
    global _sequence
    _sequence += 1
    return _sequence


async def _broadcast_loop() -> None:
    while True:
        envelope = await _broadcast_queue.get()
        dead: list[WebSocket] = []
        for ws in list(_connections):
            try:
                await ws.send_json(envelope)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            _connections.discard(ws)
        _broadcast_queue.task_done()


@router.websocket("/events")
async def events_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    logger.info("ws client connected (%d total)", len(_connections))
    try:
        # replay the current sequence number so clients can detect gaps
        await websocket.send_json({"event_type": "system.connected", "sequence": _sequence, "payload": {}})
        while True:
            # keep alive; client messages are ignored in MVP
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        logger.info("ws client disconnected (%d total)", len(_connections))


def start_gateway() -> None:
    """Subscribe the WS gateway to the EventBus (called once at app startup)."""
    bus.subscribe("*", _on_event)
    asyncio.create_task(_broadcast_loop())
