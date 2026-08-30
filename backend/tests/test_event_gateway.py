"""P1-E4-T02 — Event Gateway hardening tests.

Covers the P1-E4-T02 acceptance criteria that had no backend coverage before:

- Thread-safe publish: a sync worker thread (``asyncio.to_thread`` — the same
  threadpool FastAPI sync routes run in) publishing via the global bus reliably
  wakes the gateway loop and fans out to connected clients, gap-free.
- Bounded per-client queue: a slow/blocked client can only fill its own buffer
  (drop-oldest on overflow); it never blocks other clients and memory stays
  capped at ``MAX_CLIENT_QUEUE``.
- Explicit lifecycle: repeated ``start()`` is idempotent (single bus
  subscription, no duplicate events); ``stop()`` unsubscribes and cancels all
  sender tasks; the module-level ``start_gateway()/stop_gateway()`` used by the
  app lifespan behave the same.
- Per-project subscription: a subscribed connection receives only that
  project's events; ``unsubscribe`` clears the filter; the per-connection
  sequence stays gap-free.
- Defensive inbound frames: malformed / non-JSON / non-object / unknown-type /
  bad-subscribe frames are ignored without raising; unknown ``event_version``
  is dropped without delivery.
- WS endpoint integration: the real ``/api/v1/events`` route wires
  start_gateway → bus subscriber → per-client fan-out → wire delivery,
  including reconnect.

The frontend half of "reconnect/gap → observable reconcile" (``classifySequence``
+ ``EventRouter.reconcile``) is covered separately in frontend tests
(``frontend/src/__tests__/events.test.ts``); the backend contract here is that
sequences are gap-free per connection, so a gap is always a real drop.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.events.bus import StudioEvent, bus
from app.events.ws import (
    MAX_CLIENT_QUEUE,
    EventGateway,
    start_gateway,
    stop_gateway,
)

# Number of overflow drops to force in the bounded-queue test (any positive value).
_OVERFLOW = 20


class _FakeWs:
    """Minimal stand-in for fastapi.WebSocket: records sent envelopes."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class _BlockingWs(_FakeWs):
    """A client whose sender blocks on the first real event send (slow/half-dead)."""

    def __init__(self) -> None:
        super().__init__()
        self._block = asyncio.Event()

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)
        if payload.get("event_type") != "system.connected":
            await self._block.wait()  # never set → sender stalls on first event


def _event(event_type: str, project_id: str | None = None, event_version: int = 1) -> StudioEvent:
    return StudioEvent(
        event_type=event_type,
        entity_type="shot",
        entity_id="s1",
        project_id=project_id,
        event_version=event_version,
    )


def _real_events(sent: list[dict]) -> list[dict]:
    return [e for e in sent if e["event_type"] != "system.connected"]


async def _flush(times: int = 30) -> None:
    """Yield enough times for thread-safe hops + sender tasks to drain."""
    for _ in range(times):
        await asyncio.sleep(0)


def test_threadpool_publish_wakes_gateway_loop() -> None:
    """A sync worker thread publishing through the bus reliably reaches the loop."""

    async def scenario() -> None:
        gateway = EventGateway()
        gateway.start()
        try:
            ws = _FakeWs()
            await gateway.connect(ws)

            # Publish from a worker thread (asyncio.to_thread == the threadpool
            # FastAPI sync routes run in). on_event runs there and must hop to the
            # gateway loop without losing or reordering events.
            await asyncio.to_thread(bus.publish, _event("shot.updated", "projA"))
            await asyncio.to_thread(bus.publish, _event("shot.updated", "projA"))
            await asyncio.to_thread(bus.publish, _event("asset.created", "projA"))
            await _flush()

            events = _real_events(ws.sent)
            assert [e["sequence"] for e in events] == [1, 2, 3]
            assert [e["event_type"] for e in events] == [
                "shot.updated",
                "shot.updated",
                "asset.created",
            ]
            assert all(e["project_id"] == "projA" for e in events)
        finally:
            await gateway.stop()

    asyncio.run(scenario())


def test_slow_client_bounded_queue_and_drop_oldest() -> None:
    """A blocked client only fills its own buffer; it never blocks others."""

    async def scenario() -> None:
        gateway = EventGateway()
        gateway.start()
        try:
            slow_ws = _BlockingWs()
            slow = await gateway.connect(slow_ws)
            fast_ws = _FakeWs()
            await gateway.connect(fast_ws)

            # Let the slow client's sender pick up the first event and stall.
            bus.publish(_event("evt.0", "projA"))
            await asyncio.sleep(0.02)

            total = MAX_CLIENT_QUEUE + 1 + _OVERFLOW  # in-flight + capacity + overflow
            for i in range(1, total):
                bus.publish(_event(f"evt.{i}", "projA"))
                if i % 50 == 0:
                    await asyncio.sleep(0)
            await _flush()

            # Slow client: buffer capped at the bound; overflow dropped the oldest.
            assert slow.dropped == _OVERFLOW
            assert slow.queue.qsize() == MAX_CLIENT_QUEUE
            buffered: list[dict] = []
            while not slow.queue.empty():
                buffered.append(slow.queue.get_nowait())
            # evt.0 (seq 1) was in-flight; _OVERFLOW more were dropped oldest-first.
            assert buffered[0]["sequence"] == 2 + _OVERFLOW
            assert buffered[-1]["event_type"] == f"evt.{total - 1}"  # newest kept

            # Fast client received everything, gap-free — unaffected by the slow one.
            events = _real_events(fast_ws.sent)
            assert len(events) == total
            assert [e["sequence"] for e in events] == list(range(1, total + 1))
        finally:
            await gateway.stop()

    asyncio.run(scenario())


def test_lifecycle_repeated_start_stop_no_duplicates_or_dangling() -> None:
    """Repeated start is idempotent; stop unsubscribes and cancels sender tasks.

    Assertions are delta-based (baseline + 1) because other test files subscribe
    their own wildcard listeners to the shared bus and never clean them up; an
    absolute subscriber count would be polluted by those pre-existing listeners.
    """

    async def scenario() -> None:
        baseline = bus.subscriber_count("*")
        gateway = EventGateway()
        gateway.start()
        gateway.start()  # idempotent on the same loop
        assert bus.subscriber_count("*") == baseline + 1

        ws = _FakeWs()
        await gateway.connect(ws)
        for _ in range(3):
            bus.publish(_event("shot.updated", "projA"))
            await asyncio.sleep(0)
        await _flush()
        # Exactly once each — the double start produced no duplicate delivery.
        assert len(_real_events(ws.sent)) == 3

        await gateway.stop()
        assert bus.subscriber_count("*") == baseline
        assert gateway._clients == set()
        # Let the cancellation of the sender task settle, then assert nothing leaks.
        await _flush()
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]

        # Restart after stop works cleanly.
        gateway.start()
        assert bus.subscriber_count("*") == baseline + 1
        await gateway.stop()
        assert bus.subscriber_count("*") == baseline

    asyncio.run(scenario())


def test_module_gateway_idempotent_and_teardown() -> None:
    """The app-lifespan start_gateway/stop_gateway behave identically."""

    import app.events.ws as ws_module

    baseline = bus.subscriber_count("*")

    async def scenario() -> None:
        first = start_gateway()
        second = start_gateway()
        assert first is second
        assert bus.subscriber_count("*") == baseline + 1
        try:
            ws = _FakeWs()
            await first.connect(ws)
            bus.publish(_event("asset.created", "projA"))
            await _flush()
            assert len(_real_events(ws.sent)) == 1
        finally:
            await stop_gateway()
            assert bus.subscriber_count("*") == baseline
            assert ws_module._gateway is None

    asyncio.run(scenario())
    assert bus.subscriber_count("*") == baseline


def test_project_filtering_and_subscribe_frames() -> None:
    """Subscribed connections get only that project's events, gap-free."""

    async def scenario() -> None:
        gateway = EventGateway()
        gateway.start()
        try:
            unfiltered_ws = _FakeWs()
            await gateway.connect(unfiltered_ws)
            filtered_ws = _FakeWs()
            filtered = await gateway.connect(filtered_ws)
            gateway.handle_client_frame(filtered, '{"type": "subscribe", "project_id": "projA"}')
            assert filtered.project_id == "projA"

            for _ in range(3):
                bus.publish(_event("shot.updated", "projA"))
                bus.publish(_event("shot.updated", "projB"))
                await asyncio.sleep(0)
            await _flush()

            unfiltered = _real_events(unfiltered_ws.sent)
            filtered_events = _real_events(filtered_ws.sent)
            assert len(unfiltered) == 6  # everything flows to an unfiltered client
            assert len(filtered_events) == 3  # only projA
            assert all(e["project_id"] == "projA" for e in filtered_events)
            # per-connection sequence stays gap-free for the filtered client
            assert [e["sequence"] for e in filtered_events] == [1, 2, 3]

            # unsubscribe clears the filter → all projects flow again
            gateway.handle_client_frame(filtered, '{"type": "unsubscribe"}')
            assert filtered.project_id is None
            bus.publish(_event("shot.updated", "projB"))
            await _flush()
            filtered_events = _real_events(filtered_ws.sent)
            assert filtered_events[-1]["project_id"] == "projB"
        finally:
            await gateway.stop()

    asyncio.run(scenario())


def test_defensive_frames_and_unknown_event_version() -> None:
    """Malformed/unknown inbound frames and unknown event versions are ignored."""

    async def scenario() -> None:
        gateway = EventGateway()
        gateway.start()
        try:
            ws = _FakeWs()
            client = await gateway.connect(ws)

            for bad in (
                "not-json",
                "[]",
                '"just a string"',
                '{"type": "bogus"}',
                '{"type": "subscribe"}',
                '{"type": "subscribe", "project_id": 123}',
                '{"type": "subscribe", "project_id": ""}',
            ):
                gateway.handle_client_frame(client, bad)  # must not raise
            assert client.project_id is None  # never got subscribed by a bad frame

            # A valid frame afterwards still works.
            gateway.handle_client_frame(client, '{"type": "subscribe", "project_id": "projA"}')
            assert client.project_id == "projA"

            # Unknown event_version is dropped safely: no delivery, no raise.
            bus.publish(_event("shot.updated", "projA", event_version=99))
            await _flush()
            assert _real_events(ws.sent) == []
        finally:
            await gateway.stop()

    asyncio.run(scenario())


def test_ws_endpoint_integration_and_reconnect(client: TestClient) -> None:
    """Real /api/v1/events route: wire delivery + clean reconnect."""

    def _publish_and_receive(ws) -> dict:
        bus.publish(_event("shot.updated", "projA"))
        envelope = ws.receive_json()
        assert envelope["event_type"] == "shot.updated"
        assert envelope["project_id"] == "projA"
        return envelope

    with client.websocket_connect("/api/v1/events") as ws:
        hello = ws.receive_json()
        assert hello["event_type"] == "system.connected"
        assert hello["sequence"] == 0

        # A bus publish from the test thread (sync, outside the app loop) arrives.
        envelope = _publish_and_receive(ws)
        assert envelope["sequence"] == 1

        # Subscribe frame is accepted and subsequent project events keep flowing.
        ws.send_text('{"type": "subscribe", "project_id": "projA"}')
        bus.publish(_event("shot.updated", "projA"))
        bus.publish(_event("shot.updated", "projA"))
        assert ws.receive_json()["event_type"] == "shot.updated"
        assert ws.receive_json()["event_type"] == "shot.updated"

    # Clean disconnect + reconnect: a fresh system.connected with a fresh stream.
    with client.websocket_connect("/api/v1/events") as ws:
        assert ws.receive_json()["event_type"] == "system.connected"
        envelope = _publish_and_receive(ws)
        assert envelope["sequence"] == 1
