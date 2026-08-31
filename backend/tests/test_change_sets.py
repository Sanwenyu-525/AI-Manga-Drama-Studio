"""P2-E3-T02/T03 — risk classification + ChangeSet undo semantics.

- risk.py unit: R0 reads / R1 update_shot / R2 generate_image / unknown → R3
- undo conflict: a later user edit on the SAME field blocks undo (409 + recovery
  payload); force=true restores anyway as a fresh revision
- undo of a DIFFERENT field does not block (revision moved on, fields intact)
- batch undo per-item results (undone | conflict | skipped)
- change-set listing filters (project / run / entity / undone)
"""

import time

from fastapi.testclient import TestClient


# ---------- risk classification (unit) ----------

def test_risk_classification_levels() -> None:
    from app.agents.risk import classify_tool_operation

    read = classify_tool_operation("get_shot", {"shot_id": "s1"})
    assert read.risk_level == "R0"

    update = classify_tool_operation("update_shot", {"shot_id": "s1", "patch": {"shot_type": "close_up"}})
    assert update.risk_level == "R1"
    assert update.irreversible is False
    assert update.estimated_tasks == 1

    generate = classify_tool_operation("generate_image", {"shot_id": "s1"})
    assert generate.risk_level == "R2"
    assert generate.estimated_tasks == 1
    assert generate.estimated_cost is None  # local providers: unknown, never fabricated

    unknown = classify_tool_operation("delete_scene", {"scene_id": "s1"})
    assert unknown.risk_level == "R3"
    assert unknown.irreversible is True


def test_risk_policy_requires_approval() -> None:
    from app.agents.risk import approval_needed

    assert approval_needed("get_shot", {}) is False
    assert approval_needed("get_scene_shots", {}) is False
    assert approval_needed("update_shot", {"patch": {"shot_type": "close_up"}}) is False
    assert approval_needed("generate_image", {}) is True  # R2 default
    assert approval_needed("delete_scene", {}) is True  # R3 always


# ---------- helpers ----------

def _make_project_shot(client: TestClient, name: str = "CS") -> dict:
    project = client.post("/api/v1/projects", json={"name": name}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shots = [
        client.post(
            f"/api/v1/scenes/{scene['id']}/shots",
            json={"shot_type": "medium", "image_prompt": f"prompt {i}"},
        ).json()
        for i in range(3)
    ]
    return {"project_id": project["id"], "scene_id": scene["id"], "shots": shots}


def _wait_run(client, run_id, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish")


def _run_update(client: TestClient, ctx: dict, shot: dict, message: str) -> str:
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": message,
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    return resp.json()["id"]


# ---------- undo conflict / force ----------

def test_undo_conflict_then_force(client: TestClient) -> None:
    """Later edit overwrites the same field → 409 with recovery details; force
    restores the before-values anyway (as a NEW revision)."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_update(client, ctx, shot, "把这个镜头改成近景。")
    _wait_run(client, run_id)

    cs = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()[0]

    # user overwrites the SAME field after the agent change
    client.patch(f"/api/v1/shots/{shot['id']}", json={"revision": 2, "patch": {"shot_type": "wide"}})
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == 3

    resp = client.post(f"/api/v1/agent/change-sets/{cs['id']}/undo", json={"force": False})
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    fields = details["fields"]
    assert fields["shot_type"]["current"] == "wide"
    assert fields["shot_type"]["before"] == "medium"
    assert details["recovery"] == {"shot_type": "medium"}

    # force=True → recovery path applies the recorded before-values anyway
    forced = client.post(f"/api/v1/agent/change-sets/{cs['id']}/undo", json={"force": True})
    assert forced.status_code == 200
    restored = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert restored["shot_type"] == "medium"
    assert restored["revision"] == 4  # 1 → agent 2 → user 3 → undo 4


def test_undo_allowed_when_later_edit_touched_other_fields(client: TestClient) -> None:
    """Undo only what was NOT overwritten: a later edit on a DIFFERENT field
    leaves the agent's field restorable."""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    run_id = _run_update(client, ctx, shot, "把这个镜头改成近景。")
    _wait_run(client, run_id)

    # user edits a different field (revision moves on)
    client.patch(f"/api/v1/shots/{shot['id']}", json={"revision": 2, "patch": {"emotion": "tense"}})

    cs = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()[0]
    resp = client.post(f"/api/v1/agent/change-sets/{cs['id']}/undo", json={"force": False})
    assert resp.status_code == 200

    restored = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert restored["shot_type"] == "medium"  # agent change undone
    assert restored["emotion"] == "tense"  # user edit preserved
    assert restored["revision"] == 4


# ---------- batch undo ----------

def test_undo_run_batch_per_item_results(client: TestClient) -> None:
    """Batch undo: newest first, per-item results; a conflicted item is reported,
    the rest still succeeds — never half-silent."""
    ctx = _make_project_shot(client)
    shot_a = ctx["shots"][0]
    shot_b = ctx["shots"][1]

    run_a = _run_update(client, ctx, shot_a, "把这个镜头改成近景。")
    run_b = _run_update(client, ctx, shot_b, "把这个镜头改成特写。")
    _wait_run(client, run_a)
    _wait_run(client, run_b)

    # both shots now hold agent edits
    assert client.get(f"/api/v1/shots/{shot_a['id']}").json()["shot_type"] == "close_up"
    assert client.get(f"/api/v1/shots/{shot_b['id']}").json()["shot_type"] == "extreme_close_up"

    # user overwrites shot_b's field → run_b's undo conflicts, run_a's succeeds
    client.patch(
        f"/api/v1/shots/{shot_b['id']}",
        json={"revision": 2, "patch": {"shot_type": "wide"}},
    )

    results = client.post(f"/api/v1/agent/runs/{run_b}/change-sets/undo", json={"force": False}).json()
    assert len(results) == 1
    assert results[0]["status"] == "conflict"
    assert client.get(f"/api/v1/shots/{shot_b['id']}").json()["shot_type"] == "wide"  # untouched

    results_a = client.post(f"/api/v1/agent/runs/{run_a}/change-sets/undo", json={"force": False}).json()
    assert results_a[0]["status"] == "undone"
    assert client.get(f"/api/v1/shots/{shot_a['id']}").json()["shot_type"] == "medium"

    # re-running the batch reports the already-undone items as skipped
    again = client.post(f"/api/v1/agent/runs/{run_a}/change-sets/undo", json={"force": False}).json()
    assert again[0]["status"] == "skipped"


def test_undo_run_batch_conflict_reported(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][2]
    run_id = _run_update(client, ctx, shot, "把这个镜头改成近景。")
    _wait_run(client, run_id)

    # overwrite the same field → batch item conflicts
    client.patch(f"/api/v1/shots/{shot['id']}", json={"revision": 2, "patch": {"shot_type": "wide"}})

    results = client.post(f"/api/v1/agent/runs/{run_id}/change-sets/undo", json={"force": False}).json()
    assert results[0]["status"] == "conflict"
    # and nothing was applied
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["shot_type"] == "wide"


# ---------- listing / filters ----------

def test_change_set_listing_filters(client: TestClient) -> None:
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_update(client, ctx, shot, "把这个镜头改成近景。")
    _wait_run(client, run_id)

    by_run = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()
    assert len(by_run) == 1
    assert by_run[0]["entity_id"] == shot["id"]

    by_project = client.get("/api/v1/agent/change-sets", params={"project_id": ctx["project_id"]}).json()
    assert len(by_project) == 1

    by_entity = client.get("/api/v1/agent/change-sets", params={"entity_id": shot["id"]}).json()
    assert len(by_entity) == 1

    # undo, then the undone filter flips
    cs_id = by_run[0]["id"]
    client.post(f"/api/v1/agent/change-sets/{cs_id}/undo", json={"force": False})
    undone_list = client.get("/api/v1/agent/change-sets", params={"undone": True}).json()
    assert any(c["id"] == cs_id for c in undone_list)
    active_list = client.get("/api/v1/agent/change-sets", params={"undone": False}).json()
    assert all(c["id"] != cs_id for c in active_list)


def test_change_set_events_published(client: TestClient) -> None:
    """agent.change_set.created + agent.change_set.undone flow over the bus."""
    from app.events.bus import EVENT_AGENT_CHANGE_SET_CREATED, EVENT_AGENT_CHANGE_SET_UNDONE

    from app.events.bus import bus

    collected: list[dict] = []

    def _on(event) -> None:
        if event.event_type in (EVENT_AGENT_CHANGE_SET_CREATED, EVENT_AGENT_CHANGE_SET_UNDONE):
            collected.append({"type": event.event_type, "payload": event.payload})

    bus.subscribe("*", _on)
    try:
        ctx = _make_project_shot(client)
        shot = ctx["shots"][0]
        run_id = _run_update(client, ctx, shot, "把这个镜头改成近景。")
        _wait_run(client, run_id)

        created = [e for e in collected if e["type"] == EVENT_AGENT_CHANGE_SET_CREATED]
        assert len(created) == 1
        assert created[0]["payload"]["entity_id"] == shot["id"]
        assert created[0]["payload"]["before"] == {"shot_type": "medium"}
        assert created[0]["payload"]["after"] == {"shot_type": "close_up"}

        cs_id = client.get("/api/v1/agent/change-sets", params={"run_id": run_id}).json()[0]["id"]
        client.post(f"/api/v1/agent/change-sets/{cs_id}/undo", json={"force": False})

        undone = [e for e in collected if e["type"] == EVENT_AGENT_CHANGE_SET_UNDONE]
        assert len(undone) == 1
        assert undone[0]["payload"]["entity_id"] == shot["id"]  # the affected entity
        assert undone[0]["payload"]["compensating_change_set_id"]
        # the compensating change also publishes a created event
        assert len([e for e in collected if e["type"] == EVENT_AGENT_CHANGE_SET_CREATED]) == 2
    finally:
        try:
            bus._subscribers["*"].remove(_on)
        except (KeyError, ValueError):
            pass
