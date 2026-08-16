"""P8-T018/T019 continuity agent + warnings + transitions tests.

Covers:
- continuity check (FakeLLM rule + semantic path) → warnings persisted to DB
- warnings list / acknowledge CRUD
- fix proposal flow: warning → proposal → WAITING_HUMAN → approve → applied (shot
  mutated via ShotService + revision bump) + warning fixed
- target_type extension: existing update_shot proposals remain unaffected
- shot_transitions list (structure)
"""

import time

from fastapi.testclient import TestClient


def _make_scene(client: TestClient, n=2) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P8Continuity"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    shots = [
        client.post(
            f"/api/v1/scenes/{scene['id']}/shots",
            json={"shot_type": "medium", "image_prompt": f"prompt {i}"},
        ).json()
        for i in range(n)
    ]
    return {"project_id": project["id"], "scene_id": scene["id"], "shots": shots}


def _wait_check(client, run_id, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/continuity/runs/{run_id}").json()
        if run["status"] in ("completed", "failed", "cancelled"):
            return run
        time.sleep(0.05)
    raise TimeoutError(f"continuity run {run_id} did not finish")


def _wait_status(client, run_id, statuses, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not reach {statuses}")


def _set_emotions(client, shots, emotions: list[str]) -> None:
    for shot, emotion in zip(shots, emotions, strict=True):
        client.patch(f"/api/v1/shots/{shot['id']}", json={"revision": 1, "patch": {"emotion": emotion}})


# ---------------------------------------------------------------- check (fake LLM)
def test_continuity_check_persists_rule_and_semantic_warnings(client: TestClient) -> None:
    """Fake LLM semantic path + rule path both write open warnings on check."""
    ctx = _make_scene(client, n=2)
    shot0, shot1 = ctx["shots"]
    # rule path: shots with no camera_movement → info visual_flow warnings.
    # semantic path: emotion flip tense→calm adjacent → action_logic warning.
    _set_emotions(client, [shot0, shot1], ["tense", "calm"])

    resp = client.post("/api/v1/agent/continuity/check", json={"scene_id": ctx["scene_id"]})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    done = _wait_check(client, run_id)
    assert done["status"] == "completed"
    assert done["result"]["warnings_created"] >= 1

    warnings = client.get(f"/api/v1/scenes/{ctx['scene_id']}/continuity-warnings").json()
    assert len(warnings) >= 1
    cats = {w["category"] for w in warnings}
    assert "action_logic" in cats, f"expected semantic warning, got {cats}"
    assert "visual_flow" in cats
    # warnings reference the scene project
    assert all(w["project_id"] == ctx["project_id"] for w in warnings)
    # a semantic warning carries evidence
    sem = next(w for w in warnings if w["category"] == "action_logic")
    assert sem["evidence"].get("rule") == "fake_emotion_flip"
    assert sem["shot_id"] == shot1["id"]


def test_continuity_check_404_for_missing_scene(client: TestClient) -> None:
    resp = client.post("/api/v1/agent/continuity/check", json={"scene_id": "nope"})
    assert resp.status_code == 404


def test_warning_acknowledge_updates_status(client: TestClient) -> None:
    ctx = _make_scene(client, n=1)
    client.post("/api/v1/agent/continuity/check", json={"scene_id": ctx["scene_id"]})
    # wait for at least one warning
    warnings = _wait_any_warning(client, ctx["scene_id"])
    warning_id = warnings[0]["id"]

    acked = client.post(f"/api/v1/continuity-warnings/{warning_id}/acknowledge").json()
    assert acked["status"] == "acknowledged"
    # stop being listed among open warnings
    open_warnings = client.get(f"/api/v1/scenes/{ctx['scene_id']}/continuity-warnings").json()
    assert warning_id not in {w["id"] for w in open_warnings}
    # acknowledge again → 4xx (already acknowledged, idempotency guard)
    assert client.post(f"/api/v1/continuity-warnings/{warning_id}/acknowledge").status_code == 422


def _wait_any_warning(client, scene_id, timeout: float = 8.0) -> list:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        warnings = client.get(f"/api/v1/scenes/{scene_id}/continuity-warnings").json()
        if warnings:
            return warnings
        time.sleep(0.05)
    raise TimeoutError("no warnings produced")


# ---------------------------------------------------------------- fix proposal flow
def test_continuity_fix_proposal_approve_applies_and_marks_fixed(client: TestClient) -> None:
    """warning → continuity_fix run (WAITING_HUMAN) → approve → shot applied + fixed."""
    from app.events.bus import EVENT_CONTINUITY_WARNING_FIXED

    ctx = _make_scene(client, n=1)
    shot = ctx["shots"][0]
    # give shot an emotion so the semantic path flags it adjacent to nothing? we
    # just need a shot-scoped warning to fix; the camera_movement info warning is
    # shot-scoped, good enough.
    client.post("/api/v1/agent/continuity/check", json={"scene_id": ctx["scene_id"]})
    warning = _wait_any_warning(client, ctx["scene_id"])[0]
    assert warning["shot_id"] == shot["id"]

    before = client.get(f"/api/v1/shots/{shot['id']}").json()["revision"]

    resp = client.post(
        "/api/v1/agent/continuity/fix",
        json={"warning_id": warning["id"], "patch": {"camera_movement": "static"}},
    )
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "waiting_human"
    assert len(run["pending_proposals"]) == 1
    proposal = run["pending_proposals"][0]
    assert proposal["tool"] == "continuity_fix"
    assert proposal["base_revision"] == before

    # shot NOT mutated yet (proposal pending)
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["revision"] == before

    collected, cb = _subscribe_events({EVENT_CONTINUITY_WARNING_FIXED})
    approved = client.post(f"/api/v1/agent/proposals/{proposal['id']}/approve").json()
    _unsubscribe(cb)
    assert approved["status"] == "applied"

    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["camera_movement"] == "static"
    assert updated["revision"] == before + 1

    # warning now fixed
    warnings = client.get(f"/api/v1/scenes/{ctx['scene_id']}/continuity-warnings").json()
    assert warning["id"] not in {w["id"] for w in warnings}
    # fixed event emitted
    assert any(e["type"] == EVENT_CONTINUITY_WARNING_FIXED for e in collected)


def test_continuity_fix_reject_does_not_apply(client: TestClient) -> None:
    ctx = _make_scene(client, n=1)
    shot = ctx["shots"][0]
    client.post("/api/v1/agent/continuity/check", json={"scene_id": ctx["scene_id"]})
    warning = _wait_any_warning(client, ctx["scene_id"])[0]

    resp = client.post(
        "/api/v1/agent/continuity/fix",
        json={"warning_id": warning["id"], "patch": {"camera_movement": "pan"}},
    )
    run = resp.json()
    proposal = run["pending_proposals"][0]

    rejected = client.post(f"/api/v1/agent/proposals/{proposal['id']}/reject").json()
    assert rejected["status"] == "rejected"
    assert client.get(f"/api/v1/shots/{shot['id']}").json()["camera_movement"] is None
    # warning stays open after reject
    warnings = client.get(f"/api/v1/scenes/{ctx['scene_id']}/continuity-warnings").json()
    assert warning["id"] in {w["id"] for w in warnings}


def test_target_type_extension_update_shot_unaffected(client: TestClient) -> None:
    """Introducing continuity_fix/continuity target types must not break update_shot."""
    ctx = _make_scene(client, n=2)
    shot = ctx["shots"][1]
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    run_id = resp.json()["id"]
    waiting = _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    proposal = waiting["pending_proposals"][0]
    assert proposal["target_type"] == "shot"
    assert proposal["tool"] == "update_shot"
    approved = client.post(f"/api/v1/agent/proposals/{proposal['id']}/approve").json()
    assert approved["status"] == "applied"
    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"
    assert updated["revision"] == 2


# ---------------------------------------------------------------- transitions (structure)
def test_transitions_list_returns_structure(client: TestClient) -> None:
    """shot_transitions is structure-only: an inserted row is listed; empty scene → []."""
    from app.db.models import ShotTransition
    from app.db import session as db_session_module

    ctx = _make_scene(client, n=2)
    shot0, shot1 = ctx["shots"]
    factory = db_session_module.session_factory_provider()
    with factory() as session:
        row = ShotTransition(
            scene_id=ctx["scene_id"],
            from_shot_id=shot0["id"],
            to_shot_id=shot1["id"],
            mode="LAST_TO_FIRST",
            created_at="2026-08-01T00:00:00+00:00",
        )
        session.add(row)
        session.commit()

    transitions = client.get(f"/api/v1/scenes/{ctx['scene_id']}/transitions").json()
    assert len(transitions) == 1
    assert transitions[0]["from_shot_id"] == shot0["id"]
    assert transitions[0]["to_shot_id"] == shot1["id"]
    assert transitions[0]["mode"] == "LAST_TO_FIRST"
    assert transitions[0]["frame_from_asset_id"] is None  # no frame extraction yet

    other = _make_scene(client, n=1)
    assert client.get(f"/api/v1/scenes/{other['scene_id']}/transitions").json() == []


def _subscribe_events(event_types: set[str]):
    from app.events.bus import bus

    collected = []

    def _on(event):
        if event.event_type in event_types:
            collected.append({"type": event.event_type, "payload": event.payload})

    bus.subscribe("*", _on)
    return collected, _on


def _unsubscribe(cb) -> None:
    from app.events.bus import bus

    try:
        bus._subscribers["*"].remove(cb)
    except (KeyError, ValueError):
        pass
