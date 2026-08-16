"""P8 continuity engine tests (P8-T001..T017).

Covers (per task book):
- Scene Base State computation (env fields + character master version refs)
- Dirty-range recompute (T015): editing an early shot recomputes only N..end
- State inheritance (end → next start, design §19/§58-59)
- Rule engine (T008-T014): each rule trigger / non-trigger as pure functions
- Relevant-state hash stability (T016): unrelated field change keeps the hash
- STALE integration (T017): master switch stales active assets, never regenerates
- API shapes (scene continuity / shot continuity-state / recompute)
- Recompute idempotency
"""
import io
import time

from PIL import Image
from fastapi.testclient import TestClient

from app.db.models import Asset, Shot
from app.domain.shot import ShotUpdate
from app.services import ShotService
from app.services.continuity_service import (
    ContinuityService,
    _relevant_state_hash,
    rule_character_version,
    rule_costume,
    rule_location,
    rule_orientation_flip,
    rule_position_jump,
    rule_prop_disappearance,
    rule_prop_holder,
    rule_time_of_day,
)


def _png_bytes(width: int = 96, height: int = 96, color: tuple = (120, 30, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


def _chain(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "Cont"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes",
        json={"name": "S1", "location_id": "gym_01", "time_of_day": "NIGHT",
              "lighting": "STADIUM_LIGHT", "mood": "tense"},
    ).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def _character(client: TestClient, project_id: str, default_costume: str | None = None) -> dict:
    body = {"name": "沈亦"}
    if default_costume:
        body["default_costume_id"] = default_costume
    resp = client.post(f"/api/v1/projects/{project_id}/characters", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _import_image(client: TestClient, project_id: str, color: tuple = (1, 2, 3)) -> str:
    resp = client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": ("ref.png", _png_bytes(color=color), "image/png")},
        data={"asset_type": "image"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _state(characters: dict, environment: dict | None = None, props: dict | None = None) -> dict:
    return {"environment": environment or {}, "characters": characters, "props": props or {}}


# ---------------------------------------------------------------- base state ----

def test_scene_base_env_and_character_master_ref(client: TestClient) -> None:
    chain = _chain(client)
    char = _character(client, chain["project_id"], default_costume="costume_a")
    asset = _import_image(client, chain["project_id"])
    client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset, "name": "v1"})
    v1 = client.get(f"/api/v1/characters/{char['id']}/versions").json()[0]
    client.post(f"/api/v1/characters/{char['id']}/versions/{v1['id']}/activate")
    # host the character in a shot so it participates in the scene base
    client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"characters": [{"character_id": char["id"]}]},
    )

    import json

    from app.db.session import session_factory_provider
    from app.db.models import Character as CharacterModel

    factory = session_factory_provider()
    # CharacterCreate/DTO has no default_costume_id field — set it on the ORM directly
    with factory() as session:
        cm = session.get(CharacterModel, char["id"])
        cm.default_costume_id = "costume_a"
        session.commit()
    with factory() as session:
        cs = ContinuityService(session)
        row = cs.compute_scene_base(chain["scene_id"])
        base = json.loads(row.base_state_json)
        env = base["environment"]
        assert env["location_id"] == "gym_01"
        assert env["time_of_day"] == "NIGHT"
        assert env["lighting"] == "STADIUM_LIGHT"
        assert env["mood"] == "tense"
        cs_char = base["characters"][char["id"]]
        assert cs_char["character_version_id"] == v1["id"]
        assert cs_char["costume_id"] == "costume_a"
        assert row.state_hash


def test_scene_base_updates_on_scene_change(client: TestClient) -> None:
    chain = _chain(client)
    import json

    from app.db.session import session_factory_provider

    factory = session_factory_provider()
    with factory() as session:
        cs = ContinuityService(session)
        cs.compute_scene_base(chain["scene_id"])
        before = cs.scene_repo.get_by_scene(chain["scene_id"]).state_hash
    resp = client.patch(
        f"/api/v1/scenes/{chain['scene_id']}",
        json={"revision": 1, "patch": {"lighting": "WARM_INDOOR"}},
    )
    assert resp.status_code == 200, resp.text
    with factory() as session:
        row = ContinuityService(session).scene_repo.get_by_scene(chain["scene_id"])
        assert row is not None
        base = json.loads(row.base_state_json)
        assert base["environment"]["lighting"] == "WARM_INDOOR"
        assert row.state_hash != before


# ---------------------------------------------------------------- dirty range ----

def test_dirty_range_recomputes_only_downstream(client: TestClient) -> None:
    chain = _chain(client)
    s1 = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "dribble", "emotion": "focused"}).json()
    s2 = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "pass", "emotion": "focused"}).json()
    s3 = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "shot", "emotion": "angry"}).json()
    s4 = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "celebrate", "emotion": "happy"}).json()

    from app.db.session import session_factory_provider

    factory = session_factory_provider()
    with factory() as session:
        cs = ContinuityService(session)
        cs.compute_scene_base(chain["scene_id"])
        cs.compute_shot_states(chain["scene_id"])
        before = {r.shot_id: (r.state_hash, r.recomputed_at) for r in cs.shot_repo.list_by_scene(chain["scene_id"])}

    with factory() as session:
        upd = ShotService(session).update_shot(
            s3["id"], s3["revision"], ShotUpdate(emotion="determined"), source="user"
        )
        assert upd.revision == s3["revision"] + 1
    with factory() as session:
        cs = ContinuityService(session)
        recomputed, total = cs.compute_shot_states(chain["scene_id"], from_shot_id=s3["id"])
        after = {r.shot_id: (r.state_hash, r.recomputed_at) for r in cs.shot_repo.list_by_scene(chain["scene_id"])}
    assert after[s1["id"]] == before[s1["id"]], "shot 1 must be untouched by a shot-3 edit"
    assert after[s2["id"]] == before[s2["id"]], "shot 2 must be untouched by a shot-3 edit"
    assert after[s3["id"]] != before[s3["id"]], "shot 3 must be recomputed"
    assert after[s4["id"]] != before[s4["id"]], "shot 4 (downstream) must be recomputed"
    assert recomputed == 2
    assert total == 4


def test_state_inheritance_end_to_next_start(client: TestClient) -> None:
    chain = _chain(client)
    s1 = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "dribble", "emotion": "focused"}).json()
    s2 = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "pass", "emotion": "focused"}).json()

    from app.db.session import session_factory_provider

    factory = session_factory_provider()
    with factory() as session:
        cs = ContinuityService(session)
        cs.compute_scene_base(chain["scene_id"])
        cs.compute_shot_states(chain["scene_id"])
        sc1 = cs.get_shot_continuity(s1["id"])
        sc2 = cs.get_shot_continuity(s2["id"])
    # environment carries forward: shot 2 start environment == shot 1 end environment
    assert sc2["start_state"]["environment"] == sc1["end_state"]["environment"]
    assert isinstance(sc2["delta"], dict)


# ---------------------------------------------------------------- hash stability ----

def test_hash_stable_for_unrelated_field_change(client: TestClient) -> None:
    chain = _chain(client)
    s1 = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"action": "dribble", "emotion": "focused", "dialogue": "hello"},
    ).json()
    from app.db.session import session_factory_provider

    factory = session_factory_provider()
    with factory() as session:
        cs = ContinuityService(session)
        cs.compute_scene_base(chain["scene_id"])
        cs.compute_shot_states(chain["scene_id"])
        h1 = cs.get_shot_continuity(s1["id"])["state_hash"]
    with factory() as session:
        ShotService(session).update_shot(s1["id"], s1["revision"], ShotUpdate(dialogue="changed"), source="user")
    with factory() as session:
        h2 = ContinuityService(session).get_shot_continuity(s1["id"])["state_hash"]
    assert h1 == h2


def test_relevant_hash_deterministic() -> None:
    s = _state({"c": {"character_version_id": "v1", "costume_id": "x"}}, {"location_id": "a", "lighting": "b"})
    assert _relevant_state_hash(s, s) == _relevant_state_hash(_state({"c": {"character_version_id": "v1", "costume_id": "x"}}, {"location_id": "a", "lighting": "b"}), s)
    changed = _state({"c": {"character_version_id": "v2", "costume_id": "x"}}, {"location_id": "a", "lighting": "b"})
    assert _relevant_state_hash(s, s) != _relevant_state_hash(changed, changed)


# ---------------------------------------------------------------- rule engine ----

def test_rule_costume() -> None:
    base = _state({"c": {"costume_id": "uniform_a"}})
    start = _state({"c": {"costume_id": "uniform_b"}})
    assert any(w["code"] == "COSTUME_CHANGED" for w in rule_costume(None, start, base, "c"))
    assert rule_costume(None, _state({"c": {"costume_id": "uniform_a"}}), base, "c") == []


def test_rule_character_version() -> None:
    start = _state({"c": {"character_version_id": "v1"}})
    assert any(w["code"] == "CHARACTER_REFERENCE_OUTDATED" for w in rule_character_version(None, start, None, "c", "v2"))
    assert rule_character_version(None, start, None, "c", "v1") == []


def test_rule_location() -> None:
    r = rule_location(None, _state({}, {"location_id": "bedroom"}), _state({}, {"location_id": "gym"}))
    assert any(w["code"] == "LOCATION_CHANGED" for w in r)


def test_rule_time_of_day() -> None:
    r = rule_time_of_day(None, _state({}, {"time_of_day": "DAY"}), _state({}, {"time_of_day": "NIGHT"}))
    assert any(w["code"] == "TIME_OF_DAY_CHANGED" for w in r)


def test_rule_prop_holder() -> None:
    prev = _state({}, props={"ball": {"holder_character_id": "shenyi", "visible": True}})
    end = _state({}, props={"ball": {"holder_character_id": "coach", "visible": True}})
    assert any(w["code"] == "PROP_HOLDER_CHANGED" for w in rule_prop_holder(prev, end, end, "ball"))


def test_rule_prop_disappearance() -> None:
    prev = _state({}, props={"ball": {"holder_character_id": "shenyi", "visible": True}})
    end = _state({}, props={})
    assert any(w["code"] == "PROP_DISAPPEARED" for w in rule_prop_disappearance(prev, end, "ball"))


def test_rule_position_jump() -> None:
    prev = _state({"c": {"position": "LEFT_WING"}})
    start = _state({"c": {"position": "BENCH"}})
    assert any(w["code"] == "POSITION_JUMP" for w in rule_position_jump(prev, start, "c"))
    assert rule_position_jump(prev, _state({"c": {"position": "LEFT_WING"}}), "c") == []


def test_rule_orientation_flip() -> None:
    prev = _state({"c": {"orientation": "RIGHT"}})
    start = _state({"c": {"orientation": "LEFT"}})
    assert any(w["code"] == "ORIENTATION_FLIP" for w in rule_orientation_flip(prev, start, "c"))


# ---------------------------------------------------------------- STALE (T017) ----

def test_master_switch_stales_active_asset_no_regen(client: TestClient) -> None:
    chain = _chain(client)
    char = _character(client, chain["project_id"])
    asset1 = _import_image(client, chain["project_id"], (10, 10, 10))
    v1 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset1}).json()
    client.post(f"/api/v1/characters/{char['id']}/versions/{v1['id']}/activate")

    shot = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"characters": [{"character_id": char["id"]}]},
    ).json()

    from app.db.session import session_factory_provider

    factory = session_factory_provider()
    with factory() as session:
        cs = ContinuityService(session)
        cs.compute_scene_base(chain["scene_id"])
        cs.compute_shot_states(chain["scene_id"])
        # attach a ready active asset to the shot (as the representation of generated work)
        a1 = Asset(project_id=chain["project_id"], type="image", name="a1.png", status="ready", source_type="generated")
        session.add(a1)
        session.flush()
        from sqlalchemy import update as sa_update

        session.execute(
            sa_update(Shot).where(Shot.id == shot["id"]).values(active_image_asset_id=a1.id)
        )
        session.commit()
        shot_with_asset = session.get(Shot, shot["id"])
        active_before = shot_with_asset.active_image_asset_id
        assert active_before == a1.id

    # activate a new master version → the hook recomputes + stales the active asset
    asset2 = _import_image(client, chain["project_id"], (20, 20, 20))
    v2 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset2}).json()
    client.post(f"/api/v1/characters/{char['id']}/versions/{v2['id']}/activate")

    with factory() as session:
        shot_model = session.get(Shot, shot["id"])
        active_asset = session.get(Asset, shot_model.active_image_asset_id)
        assert active_asset.status == "stale"
        # no new generation/regeneration was created for the shot
        from app.db.models import Generation

        gens = session.query(Generation).filter(Generation.shot_id == shot["id"]).count()
    assert gens == 0


# ---------------------------------------------------------------- API ----

def test_scene_continuity_api_shape(client: TestClient) -> None:
    chain = _chain(client)
    char = _character(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])
    v1 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset}).json()
    client.post(f"/api/v1/characters/{char['id']}/versions/{v1['id']}/activate")
    shot = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"action": "dribble", "characters": [{"character_id": char["id"]}]},
    ).json()

    resp = client.get(f"/api/v1/scenes/{chain['scene_id']}/continuity")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["scene_id"] == chain["scene_id"]
    assert "base_state" in data and "base_state_hash" in data
    assert len(data["shots"]) == 1
    one = data["shots"][0]
    assert one["shot_id"] == shot["id"]
    for key in ("start_state", "end_state", "delta", "state_hash", "warnings"):
        assert key in one
    assert isinstance(one["warnings"], list)


def test_shot_continuity_state_api_shape(client: TestClient) -> None:
    chain = _chain(client)
    shot = client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "run", "emotion": "calm"}).json()
    resp = client.get(f"/api/v1/shots/{shot['id']}/continuity-state")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["shot_id"] == shot["id"]
    assert data["start_state"]["environment"]["location_id"] == "gym_01"
    assert data["end_state"]["environment"]["location_id"] == "gym_01"
    assert isinstance(data["delta"], dict)
    assert data["state_hash"]
    assert isinstance(data["warnings"], list)


def test_recompute_idempotent(client: TestClient) -> None:
    chain = _chain(client)
    for _ in range(3):
        client.post(f"/api/v1/scenes/{chain['scene_id']}/shots", json={"action": "act"})
    r1 = client.post(f"/api/v1/scenes/{chain['scene_id']}/continuity/recompute")
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["recomputed_shots"] == 3
    assert b1["total_shots"] == 3
    assert b1["state_hash"]
    r2 = client.post(f"/api/v1/scenes/{chain['scene_id']}/continuity/recompute")
    assert r2.json()["state_hash"] == b1["state_hash"]
    before = client.get(f"/api/v1/scenes/{chain['scene_id']}/continuity").json()
    _ = client.post(f"/api/v1/scenes/{chain['scene_id']}/continuity/recompute")
    after = client.get(f"/api/v1/scenes/{chain['scene_id']}/continuity").json()
    assert [s["state_hash"] for s in after["shots"]] == [s["state_hash"] for s in before["shots"]]
"""P8-T018/T019 continuity agent + warnings + transitions tests.

Covers:
- continuity check (FakeLLM rule + semantic path) → warnings persisted to DB
- warnings list / acknowledge CRUD
- fix proposal flow: warning → proposal → WAITING_HUMAN → approve → applied (shot
  mutated via ShotService + revision bump) + warning fixed
- target_type extension: existing update_shot proposals remain unaffected
- shot_transitions list (structure)
"""

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
