"""P2-T007/T008 CharacterVersion tests (database-v0.1 §7, domain-model-design §31/§32).

Covers the P2 acceptance path:
- Create visual versions (vN+1, stale by default, character.version.created event)
- Activate (old active -> stale, master pointer flip, character.version.activated event; idempotent)
- List ordering by version_number; is_master flag
- Validation: unknown character / asset 404, cross-project asset 422, foreign version 404
- Soft-deleted character unavailable; soft-deleted versions excluded
- P3-T012 link: generation provenance records CHARACTER_REFERENCE for master versions
"""

import io

from PIL import Image
from fastapi.testclient import TestClient

from app.events.bus import bus


def _event_spy():
    seen: list = []
    bus.subscribe("*", lambda e: seen.append(e))
    return seen


def _png_bytes(width: int = 96, height: int = 96, color: tuple = (120, 30, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


def _create_chain(client: TestClient) -> dict[str, str]:
    project = client.post("/api/v1/projects", json={"name": "角色版本"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def _create_character(client: TestClient, project_id: str, name: str = "沈亦") -> dict:
    resp = client.post(f"/api/v1/projects/{project_id}/characters", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _import_image(client: TestClient, project_id: str, color: tuple = (1, 2, 3)) -> str:
    """Import a PNG as a project-scope asset; returns asset id."""
    resp = client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": ("ref.png", _png_bytes(color=color), "image/png")},
        data={"asset_type": "image"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- creation: vN+1, stale default, event ---------------------------------

def test_create_versions_numbers_and_events(client: TestClient) -> None:
    seen = _event_spy()
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    asset1 = _import_image(client, chain["project_id"], (10, 10, 10))

    v1 = client.post(
        f"/api/v1/characters/{char['id']}/versions",
        json={"asset_id": asset1, "name": "初版", "description": "校服"},
    )
    assert v1.status_code == 201
    body = v1.json()
    assert body["version_number"] == 1
    assert body["status"] == "stale", "new version must default to stale (no auto activation)"
    assert body["is_master"] is False
    assert body["asset_id"] == asset1
    assert body["name"] == "初版"

    # character read exposes master_version_id (still None)
    char_read = client.get(f"/api/v1/characters/{char['id']}").json()
    assert char_read["master_version_id"] is None

    # second version -> v2 (max+1)
    asset2 = _import_image(client, chain["project_id"], (20, 20, 20))
    v2 = client.post(
        f"/api/v1/characters/{char['id']}/versions",
        json={"asset_id": asset2},
    )
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2
    assert v2.json()["status"] == "stale"

    created = [e for e in seen if e.event_type == "character.version.created"]
    assert len(created) == 2
    assert {e.payload["version_number"] for e in created} == {1, 2}
    assert created[0].entity_id == char["id"]


def test_create_version_validation(client: TestClient) -> None:
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])

    # unknown character -> 404
    resp = client.post(
        "/api/v1/characters/nope/versions", json={"asset_id": asset}
    )
    assert resp.status_code == 404

    # unknown asset -> 404
    resp = client.post(
        f"/api/v1/characters/{char['id']}/versions", json={"asset_id": "asset_nope"}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    # cross-project asset -> 422
    other = client.post("/api/v1/projects", json={"name": "其他项目"}).json()
    foreign_asset = _import_image(client, other["id"], (99, 99, 99))
    resp = client.post(
        f"/api/v1/characters/{char['id']}/versions", json={"asset_id": foreign_asset}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_soft_deleted_character_unavailable(client: TestClient) -> None:
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])

    client.delete(f"/api/v1/characters/{char['id']}")  # soft delete
    resp = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset})
    assert resp.status_code == 404
    assert client.get(f"/api/v1/characters/{char['id']}/versions").status_code == 404


# --- activation: flip master + old stale + event ---------------------------

def test_activate_flips_master_and_stales_previous(client: TestClient) -> None:
    seen = _event_spy()
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    a1 = _import_image(client, chain["project_id"], (1, 1, 1))
    a2 = _import_image(client, chain["project_id"], (2, 2, 2))
    v1 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": a1}).json()
    v2 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": a2}).json()

    # activate v1 first
    act1 = client.post(f"/api/v1/characters/{char['id']}/versions/{v1['id']}/activate")
    assert act1.status_code == 200
    assert act1.json()["status"] == "active"
    assert act1.json()["is_master"] is True

    char_read = client.get(f"/api/v1/characters/{char['id']}").json()
    assert char_read["master_version_id"] == v1["id"]

    # activate v2 -> v1 becomes stale, master moves to v2
    act2 = client.post(f"/api/v1/characters/{char['id']}/versions/{v2['id']}/activate")
    assert act2.status_code == 200
    assert act2.json()["status"] == "active"
    assert act2.json()["is_master"] is True

    char_read = client.get(f"/api/v1/characters/{char['id']}").json()
    assert char_read["master_version_id"] == v2["id"]

    versions = client.get(f"/api/v1/characters/{char['id']}/versions").json()
    by_num = {v["version_number"]: v for v in versions}
    assert by_num[1]["status"] == "stale"
    assert by_num[2]["status"] == "active"
    assert by_num[2]["is_master"] is True
    assert by_num[1]["is_master"] is False

    activated = [e for e in seen if e.event_type == "character.version.activated"]
    assert len(activated) == 2
    last = activated[-1]
    assert last.payload == {
        "character_id": char["id"],
        "version_id": v2["id"],
        "version_number": 2,
        "asset_id": a2,
    }


def test_activate_is_idempotent(client: TestClient) -> None:
    seen = _event_spy()
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])
    v1 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset}).json()

    first = client.post(f"/api/v1/characters/{char['id']}/versions/{v1['id']}/activate")
    assert first.status_code == 200
    second = client.post(f"/api/v1/characters/{char['id']}/versions/{v1['id']}/activate")
    assert second.status_code == 200
    assert second.json()["status"] == "active"
    assert second.json()["is_master"] is True

    # exactly one activated event (re-activation is a no-op)
    activated = [e for e in seen if e.event_type == "character.version.activated"]
    assert len(activated) == 1


def test_activate_foreign_version_404(client: TestClient) -> None:
    chain = _create_chain(client)
    char_a = _create_character(client, chain["project_id"], "沈亦")
    char_b = _create_character(client, chain["project_id"], "顾言")
    asset = _import_image(client, chain["project_id"])
    va = client.post(f"/api/v1/characters/{char_a['id']}/versions", json={"asset_id": asset}).json()

    # char_b trying to activate char_a's version -> 404
    resp = client.post(f"/api/v1/characters/{char_b['id']}/versions/{va['id']}/activate")
    assert resp.status_code == 404
    # unknown version id -> 404
    resp = client.post(f"/api/v1/characters/{char_a['id']}/versions/nope/activate")
    assert resp.status_code == 404


# --- listing ---------------------------------------------------------------

def test_list_versions_ordered(client: TestClient) -> None:
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    a1 = _import_image(client, chain["project_id"], (1, 1, 1))
    a2 = _import_image(client, chain["project_id"], (2, 2, 2))
    a3 = _import_image(client, chain["project_id"], (3, 3, 3))
    client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": a1})
    client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": a2})
    v3 = client.post(f"/api/v1/characters/{char['id']}/versions", json={"asset_id": a3}).json()

    listed = client.get(f"/api/v1/characters/{char['id']}/versions").json()
    assert [v["version_number"] for v in listed] == [1, 2, 3]
    assert [v["is_master"] for v in listed] == [False, False, False]

    client.post(f"/api/v1/characters/{char['id']}/versions/{v3['id']}/activate")
    listed = client.get(f"/api/v1/characters/{char['id']}/versions").json()
    assert listed[2]["is_master"] is True

    # unknown character -> 404
    assert client.get("/api/v1/characters/nope/versions").status_code == 404


# --- P3-T012 provenance link ------------------------------------------------

def test_generation_records_character_reference(client: TestClient) -> None:
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])
    version = client.post(
        f"/api/v1/characters/{char['id']}/versions", json={"asset_id": asset}
    ).json()
    client.post(f"/api/v1/characters/{char['id']}/versions/{version['id']}/activate")

    shot = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, gym",
              "character_ids": [char["id"]]},
    )
    assert shot.status_code == 201, shot.text
    shot_id = shot.json()["id"]

    import asyncio
    from app.generations.worker import run_generation

    created = client.post(f"/api/v1/shots/{shot_id}/generations", json={"type": "image"})
    assert created.status_code == 202
    gen_id = created.json()["id"]
    asyncio.run(run_generation(gen_id))

    inputs = client.get(f"/api/v1/generations/{gen_id}/inputs").json()
    refs = [i for i in inputs["inputs"] if i["reference_type"] == "CHARACTER_REFERENCE"]
    assert len(refs) == 1
    ref = refs[0]
    assert ref["role"] == "character_reference"
    assert ref["reference_id"] == version["id"]
    import json as _json

    meta = _json.loads(ref["metadata_json"])
    assert meta["character_id"] == char["id"]
    assert meta["asset_id"] == asset


def test_generation_skips_character_without_master(client: TestClient) -> None:
    """A character with no activated (master) version contributes no CHARACTER_REFERENCE."""
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    shot = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style",
              "character_ids": [char["id"]]},
    ).json()

    import asyncio
    from app.generations.worker import run_generation

    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    gen_id = created.json()["id"]
    asyncio.run(run_generation(gen_id))

    inputs = client.get(f"/api/v1/generations/{gen_id}/inputs").json()
    assert all(i["reference_type"] != "CHARACTER_REFERENCE" for i in inputs["inputs"])
