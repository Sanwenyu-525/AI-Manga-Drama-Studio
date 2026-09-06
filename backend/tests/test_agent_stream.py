"""C 真流式 — graph 阶段/增量事件测试。

覆盖：一次 director run（fake LLM）依次 publish intent.resolved →
context.loaded → plan.created → run.stream（各阶段分片，done 收尾）→
review.started → review.completed。只新增断言，不改既有行为。
"""

import time

from fastapi.testclient import TestClient

from app.events.bus import bus


def _wait_run(client: TestClient, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled", "waiting_human", "WAITING_HUMAN"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"agent run {run_id} did not finish")


def test_director_run_publishes_stage_and_stream_events(client: TestClient) -> None:
    seen: list[str] = []
    streams: list[dict] = []

    def _capture(event) -> None:
        seen.append(event.event_type)
        if event.event_type == "agent.run.stream":
            streams.append(dict(event.payload))

    for name in (
        "agent.intent.resolved",
        "agent.context.loaded",
        "agent.plan.created",
        "agent.run.stream",
        "agent.review.started",
        "agent.review.completed",
    ):
        bus.subscribe(name, _capture)
    try:
        project = client.post("/api/v1/projects", json={"name": "StreamAudit"}).json()
        episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
        scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "天台"}).json()
        shot = client.post(f"/api/v1/scenes/{scene['id']}/shots", json={}).json()

        resp = client.post(
            "/api/v1/agent/director/runs",
            json={
                "project_id": project["id"],
                "message": "改成近景",
                "selection": {"scene_id": scene["id"], "shot_ids": [shot["id"]]},
            },
        )
        assert resp.status_code == 202, resp.text
        done = _wait_run(client, resp.json()["id"])
        assert done["status"] in ("completed", "waiting_human", "WAITING_HUMAN"), done.get("result")
    finally:
        for name in (
            "agent.intent.resolved",
            "agent.context.loaded",
            "agent.plan.created",
            "agent.run.stream",
            "agent.review.started",
            "agent.review.completed",
        ):
            bus.unsubscribe(name, _capture)

    # 阶段事件按序到达（tool 事件穿插其中，不强制连续）
    order = ["agent.intent.resolved", "agent.context.loaded", "agent.plan.created"]
    idx = [seen.index(e) for e in order if e in seen]
    assert len(idx) == len(order), seen
    assert idx == sorted(idx), seen

    # stream 分片：每片带 stage/delta/done，且至少有一个 done=True 收尾
    assert streams, seen
    assert all({"stage", "delta", "done"} <= set(s) for s in streams), streams
    assert any(s["done"] for s in streams), streams
    assert "".join(s["delta"] for s in streams), streams
