"""WebSocket event gateway (api-event-contract §49-53): /api/v1/events.

Every Studio event is broadcast with the standard envelope (event_id, event_type,
event_version, project_id, entity_type, entity_id, timestamp, sequence, payload).

P1-E4-T02 hardening:

- Thread-safe publish: sync services run in the threadpool and call ``bus.publish``
  there — a plain ``asyncio.Queue.put_nowait`` from a non-loop thread is NOT
  thread-safe. The gateway subscriber hops to the gateway event loop via
  ``loop.call_soon_threadsafe`` and never blocks the publisher.
- Per-connection bounded queue + dedicated sender task: a slow or half-dead client
  can only fill its own buffer (drop-oldest on overflow — the client observes the
  sequence gap and reconciles); it can never block other clients or the loop.
- Per-connection sequence numbering: each client sees a gap-free stream of the
  events it actually receives, so a gap is ALWAYS a real drop worth reconciling
  (global numbering would report false gaps for filtered deliveries).
- Explicit lifecycle: ``start_gateway()`` is idempotent and returns the gateway;
  ``stop_gateway()`` unsubscribes from the bus and cancels all tasks — repeated
  app lifespans produce no duplicate events and no dangling tasks.
- Optional per-project subscription: after connecting, a client may send
  ``{"type": "subscribe", "project_id": "..."}`` (JSON). A subscribed connection
  receives only that project's events; ``{"type": "unsubscribe"}`` clears it.
- Defensive inbound frames: malformed / non-JSON / unknown-type frames are logged
  and safely ignored (contract §137); outgoing events with an unknown
  ``event_version`` are dropped with a log line.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.events.bus import StudioEvent, bus

logger = get_logger("events.ws")

router = APIRouter(tags=["events"])

# Per-connection buffer bound (P1-E2-T02/T03 rule: memory must stay capped). A
# client that cannot keep up loses the OLDEST events and reconciles via REST —
# the WS is a hint channel, never the source of truth.
MAX_CLIENT_QUEUE = 256

SUPPORTED_EVENT_VERSIONS = (1,)


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


@dataclass(eq=False)
class _Client:
    """Per-connection state. eq=False keeps identity hashing so the gateway can
    hold clients in a set (add/discard by object identity — each connection is
    a unique object; dataclass value-equality is never wanted here)."""
    ws: WebSocket
    queue: asyncio.Queue[dict[str, Any] | None]
    project_id: str | None = None
    sequence: int = 0
    dropped: int = 0
    sender_task: asyncio.Task | None = field(default=None, repr=False)


class EventGateway:
    """Bus subscriber + per-client fan-out on the gateway event loop."""

    def __init__(self) -> None:
        self._clients: set[_Client] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False

    # ---- bus subscriber (sync; may be invoked from ANY thread) ----------------

    def on_event(self, event: StudioEvent) -> None:
        """EventBus subscriber: hop to the gateway loop without blocking the caller.

        Safe to call from threadpool threads (sync service commits) and from the
        loop itself (async routes). Never raises.
        """
        if event.event_version not in SUPPORTED_EVENT_VERSIONS:
            logger.warning(
                "dropping event %s (%s): unknown event_version %s",
                event.event_id, event.event_type, event.event_version,
            )
            return
        loop = self._loop
        if loop is None or loop.is_closed() or not self._started:
            return
        try:
            loop.call_soon_threadsafe(self._fan_out, event)
        except RuntimeError:
            # Loop died between the checks and the call — shutting down; drop.
            logger.debug("gateway loop closed; dropped event %s", event.event_id)

    # ---- fan-out (runs on the gateway loop) -----------------------------------

    def _fan_out(self, event: StudioEvent) -> None:
        for client in list(self._clients):
            if client.project_id is not None and event.project_id != client.project_id:
                continue  # project-filtered connection
            client.sequence += 1
            payload = _envelope(event, client.sequence)
            try:
                client.queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop the OLDEST buffered payload to admit the newest: the client
                # observes the sequence gap and reconciles from REST (bootstrap).
                try:
                    client.queue.get_nowait()
                    client.dropped += 1
                    client.queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):  # pragma: no cover — race
                    pass
                logger.warning(
                    "ws client queue overflow (dropped_total=%d); client must reconcile",
                    client.dropped,
                )

    async def _sender(self, client: _Client) -> None:
        """Dedicated sender: a slow client blocks (and drops) only itself."""
        try:
            while True:
                payload = await client.queue.get()
                if payload is None:  # shutdown sentinel
                    break
                await client.ws.send_json(payload)
        except Exception as exc:  # noqa: BLE001 — send failure / cancellation
            logger.debug("ws sender task ending (client gone): %s", exc)
        finally:
            self._clients.discard(client)

    # ---- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        """Bind to the running loop and subscribe to the bus (idempotent per loop)."""
        self._loop = asyncio.get_running_loop()
        if self._started:
            return
        self._started = True
        bus.subscribe("*", self.on_event)
        logger.info("event gateway started")

    async def stop(self) -> None:
        """Unsubscribe and tear down every client task (no dangling work)."""
        if not self._started:
            return
        self._started = False
        bus.unsubscribe("*", self.on_event)
        for client in list(self._clients):
            if client.sender_task is not None:
                client.sender_task.cancel()
        self._clients.clear()
        logger.info("event gateway stopped")

    # ---- connection plumbing ------------------------------------------------------

    async def connect(self, websocket: WebSocket) -> _Client:
        await websocket.accept()
        client = _Client(ws=websocket, queue=asyncio.Queue(maxsize=MAX_CLIENT_QUEUE))
        client.sender_task = asyncio.create_task(self._sender(client))
        self._clients.add(client)
        logger.info("ws client connected (%d total)", len(self._clients))
        await websocket.send_json(
            {"event_type": "system.connected", "sequence": client.sequence, "payload": {}}
        )
        return client

    async def disconnect(self, client: _Client) -> None:
        self._clients.discard(client)
        if client.sender_task is not None:
            client.sender_task.cancel()
        logger.info("ws client disconnected (%d total)", len(self._clients))

    def handle_client_frame(self, client: _Client, raw: str) -> None:
        """Parse one inbound frame defensively; unknown/malformed → log + ignore."""
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            logger.info("ws: ignoring malformed client frame")
            return
        if not isinstance(frame, dict):
            logger.info("ws: ignoring non-object client frame")
            return
        frame_type = frame.get("type")
        if frame_type == "subscribe":
            project_id = frame.get("project_id")
            if isinstance(project_id, str) and project_id:
                client.project_id = project_id
                logger.info("ws client subscribed to project %s", project_id)
            else:
                logger.info("ws: ignoring subscribe frame without project_id")
        elif frame_type == "unsubscribe":
            client.project_id = None
            logger.info("ws client subscription cleared")
        else:
            logger.info("ws: ignoring unknown client frame type %r", frame_type)


_gateway: EventGateway | None = None


def start_gateway() -> EventGateway:
    """Bind the process-wide gateway to the running loop (idempotent — repeated
    startup calls on the same loop return the existing gateway, never a second
    bus subscription)."""
    global _gateway
    if _gateway is not None and _gateway._started and _gateway._loop is asyncio.get_running_loop():
        return _gateway
    if _gateway is None:
        _gateway = EventGateway()
    _gateway.start()
    return _gateway


async def stop_gateway() -> None:
    """Full teardown: unsubscribe + cancel tasks (called from lifespan shutdown)."""
    global _gateway
    if _gateway is None:
        return
    gateway, _gateway = _gateway, None
    await gateway.stop()


@router.websocket("/events")
async def events_endpoint(websocket: WebSocket) -> None:
    gateway = start_gateway()
    client = await gateway.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            gateway.handle_client_frame(client, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await gateway.disconnect(client)
