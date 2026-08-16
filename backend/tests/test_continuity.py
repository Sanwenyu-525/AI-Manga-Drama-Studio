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
