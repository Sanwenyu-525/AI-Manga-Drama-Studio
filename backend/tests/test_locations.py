"""P2-T009 Location + LocationVersion tests (database-v0.1 §6, domain-model-design §35/§36).

Covers the P2 acceptance path, mirroring test_character_versions.py:
- Location CRUD (soft delete, revision optimistic concurrency 409)
- Create visual versions (vN+1, stale by default, location.version.created event)
- Activate (old active -> stale, master pointer flip, activated event; idempotent)
- List ordering by version_number; is_master flag
- Validation: unknown location / asset 404, cross-project asset 422, foreign version 404
- Soft-deleted location unavailable; soft-deleted versions excluded
- scenes.location_id service-layer validation (404 / 422)
"""

import io

from PIL import Image
from fastapi.testclient import TestClient

from app.events.bus import bus


def _event_spy():
    seen: list = []
    bus.subscribe("*", lambda e: seen.append(e))
    return seen


def _png_bytes(width: int = 96, height: int = 96, color: tuple = (90, 140, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


def _create_project(client: TestClient, name: str = "地点项目") -> dict:
    resp = client.post("/api/v1/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_chain(client: TestClient) -> dict[str, str]:
    project = _create_project(client)
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def _create_location(client: TestClient, project_id: str, name: str = "学校体育馆") -> dict:
    resp = client.post(f"/api/v1/projects/{project_id}/locations", json={"name": name})
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


# --- Location CRUD ---------------------------------------------------------

def test_location_crud_and_events(client: TestClient) -> None:
    seen = _event_spy()
    project = _create_project(client)

    created = client.post(
        f"/api/v1/projects/{project['id']}/locations",
        json={"name": "学校体育馆", "description": "室内篮球场", "visual_prompt": "gym manga style"},
    )
    assert created.status_code == 201
    body = created.json()
    loc_id = body["id"]
    assert body["name"] == "学校体育馆"
    assert body["revision"] == 1
    assert body["project_id"] == project["id"]
    assert body["master_version_id"] is None

    # update (revision bump)
    updated = client.patch(
        f"/api/v1/locations/{loc_id}",
        json={"revision": 1, "patch": {"description": "室外操场"}},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "室外操场"
    assert updated.json()["revision"] == 2

    # stale revision -> 409
    conflict = client.patch(
        f"/api/v1/locations/{loc_id}",
        json={"revision": 1, "patch": {"description": "x"}},
    )
    assert conflict.status_code == 409

    # unknown location -> 404
    assert client.get("/api/v1/locations/nope").status_code == 404

    # list
    listed = client.get(f"/api/v1/projects/{project['id']}/locations").json()
    assert [x["id"] for x in listed] == [loc_id]

    # soft delete
    deleted = client.delete(f"/api/v1/locations/{loc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/v1/locations/{loc_id}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/locations").json() == []

    created_events = [e for e in seen if e.event_type == "location.created"]
    updated_events = [e for e in seen if e.event_type == "location.updated"]
    deleted_events = [e for e in seen if e.event_type == "location.deleted"]
    assert len(created_events) == 1
    assert len(updated_events) == 1
    assert len(deleted_events) == 1
    assert created_events[0].entity_id == loc_id
    assert updated_events[0].payload == {"revision": 2, "changed_fields": ["description"]}


def test_location_cross_project_validation(client: TestClient) -> None:
    _create_project(client, "A")
    _create_project(client, "B")

    # list requires a real project -> 404
    assert client.get("/api/v1/projects/nope/locations").status_code == 404
    # create under missing project -> 404
    assert client.post("/api/v1/projects/nope/locations", json={"name": "x"}).status_code == 404


# --- versions --------------------------------------------------------------

def test_create_versions_numbers_and_events(client: TestClient) -> None:
    seen = _event_spy()
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])
    asset1 = _import_image(client, chain["project_id"], (10, 10, 10))

    v1 = client.post(
        f"/api/v1/locations/{loc['id']}/versions",
        json={"asset_id": asset1, "name": "体育馆初版"},
    )
    assert v1.status_code == 201
    body = v1.json()
    assert body["version_number"] == 1
    assert body["status"] == "stale", "new version must default to stale"
    assert body["is_master"] is False
    assert body["asset_id"] == asset1

    loc_read = client.get(f"/api/v1/locations/{loc['id']}").json()
    assert loc_read["master_version_id"] is None

    asset2 = _import_image(client, chain["project_id"], (20, 20, 20))
    v2 = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": asset2})
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2
    assert v2.json()["status"] == "stale"

    created = [e for e in seen if e.event_type == "location.version.created"]
    assert len(created) == 2
    assert {e.payload["version_number"] for e in created} == {1, 2}


def test_create_version_validation(client: TestClient) -> None:
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])

    # unknown location -> 404
    assert client.post("/api/v1/locations/nope/versions", json={"asset_id": asset}).status_code == 404
    # unknown asset -> 404
    resp = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": "asset_nope"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"
    # cross-project asset -> 422
    other = _create_project(client, "其他项目")
    foreign_asset = _import_image(client, other["id"], (99, 99, 99))
    resp = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": foreign_asset})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_soft_deleted_location_unavailable(client: TestClient) -> None:
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])

    client.delete(f"/api/v1/locations/{loc['id']}")
    assert client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": asset}).status_code == 404
    assert client.get(f"/api/v1/locations/{loc['id']}/versions").status_code == 404


# --- activation ------------------------------------------------------------

def test_activate_flips_master_and_stales_previous(client: TestClient) -> None:
    seen = _event_spy()
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])
    a1 = _import_image(client, chain["project_id"], (1, 1, 1))
    a2 = _import_image(client, chain["project_id"], (2, 2, 2))
    v1 = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": a1}).json()
    v2 = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": a2}).json()

    act1 = client.post(f"/api/v1/locations/{loc['id']}/versions/{v1['id']}/activate")
    assert act1.status_code == 200
    assert act1.json()["status"] == "active"
    assert act1.json()["is_master"] is True
    assert client.get(f"/api/v1/locations/{loc['id']}").json()["master_version_id"] == v1["id"]

    act2 = client.post(f"/api/v1/locations/{loc['id']}/versions/{v2['id']}/activate")
    assert act2.status_code == 200
    assert act2.json()["status"] == "active"
    assert act2.json()["is_master"] is True
    assert client.get(f"/api/v1/locations/{loc['id']}").json()["master_version_id"] == v2["id"]

    versions = client.get(f"/api/v1/locations/{loc['id']}/versions").json()
    by_num = {v["version_number"]: v for v in versions}
    assert by_num[1]["status"] == "stale"
    assert by_num[2]["status"] == "active"
    assert by_num[2]["is_master"] is True
    assert by_num[1]["is_master"] is False

    activated = [e for e in seen if e.event_type == "location.version.activated"]
    assert len(activated) == 2
    last = activated[-1]
    assert last.payload == {
        "location_id": loc["id"],
        "version_id": v2["id"],
        "version_number": 2,
        "asset_id": a2,
    }


def test_activate_is_idempotent(client: TestClient) -> None:
    seen = _event_spy()
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])
    v1 = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": asset}).json()

    first = client.post(f"/api/v1/locations/{loc['id']}/versions/{v1['id']}/activate")
    assert first.status_code == 200
    second = client.post(f"/api/v1/locations/{loc['id']}/versions/{v1['id']}/activate")
    assert second.status_code == 200
    assert second.json()["status"] == "active"
    assert second.json()["is_master"] is True

    activated = [e for e in seen if e.event_type == "location.version.activated"]
    assert len(activated) == 1


def test_activate_foreign_version_404(client: TestClient) -> None:
    chain = _create_chain(client)
    loc_a = _create_location(client, chain["project_id"], "体育馆")
    loc_b = _create_location(client, chain["project_id"], "卧室")
    asset = _import_image(client, chain["project_id"])
    va = client.post(f"/api/v1/locations/{loc_a['id']}/versions", json={"asset_id": asset}).json()

    resp = client.post(f"/api/v1/locations/{loc_b['id']}/versions/{va['id']}/activate")
    assert resp.status_code == 404
    resp = client.post(f"/api/v1/locations/{loc_a['id']}/versions/nope/activate")
    assert resp.status_code == 404


def test_list_versions_ordered(client: TestClient) -> None:
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])
    a1 = _import_image(client, chain["project_id"], (1, 1, 1))
    a2 = _import_image(client, chain["project_id"], (2, 2, 2))
    a3 = _import_image(client, chain["project_id"], (3, 3, 3))
    client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": a1})
    client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": a2})
    v3 = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": a3}).json()

    listed = client.get(f"/api/v1/locations/{loc['id']}/versions").json()
    assert [v["version_number"] for v in listed] == [1, 2, 3]
    assert [v["is_master"] for v in listed] == [False, False, False]

    client.post(f"/api/v1/locations/{loc['id']}/versions/{v3['id']}/activate")
    listed = client.get(f"/api/v1/locations/{loc['id']}/versions").json()
    assert listed[2]["is_master"] is True

    assert client.get("/api/v1/locations/nope/versions").status_code == 404


# --- scenes.location_id service-layer validation ---------------------------

def test_scene_location_id_validated(client: TestClient) -> None:
    chain = _create_chain(client)
    loc = _create_location(client, chain["project_id"])

    # valid location on create
    assert client.get(f"/api/v1/locations/{loc['id']}").status_code == 200
    created = client.post(
        f"/api/v1/episodes/{chain['episode_id']}/scenes",
        json={"name": "S2", "location_id": loc["id"]},
    )
    assert created.status_code == 201
    assert created.json()["location_id"] == loc["id"]

    # unknown location uuid -> 404 (real-format UUID reference must exist)
    unknown_uuid = "11111111-2222-3333-4444-555555555555"
    resp = client.post(
        f"/api/v1/episodes/{chain['episode_id']}/scenes",
        json={"name": "S3", "location_id": unknown_uuid},
    )
    assert resp.status_code == 404

    # update scene with invalid location uuid -> 404/422
    resp = client.patch(
        f"/api/v1/scenes/{created.json()['id']}",
        json={"revision": 1, "patch": {"location_id": unknown_uuid}},
    )
    assert resp.status_code in (404, 422)

    # legacy free-text location stays valid (weak ref backward compatibility)
    free_text = client.post(
        f"/api/v1/episodes/{chain['episode_id']}/scenes",
        json={"name": "S4", "location_id": "体育馆"},
    )
    assert free_text.status_code == 201
    assert free_text.json()["location_id"] == "体育馆"
