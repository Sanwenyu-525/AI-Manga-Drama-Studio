"""P2-T010 Costume tests (database-v0.1 §8, domain-model-design §33).

Covers:
- Costume CRUD (soft delete, revision optimistic concurrency 409, events)
- reference_asset_id / character_id validation (404 / cross-project 422)
- shot_characters.costume_id: backward-compatible 'characters' extension on
  shot create + PATCH /shots/{id} records costume_id on link rows.
"""

import io

from PIL import Image
from fastapi.testclient import TestClient

from app.events.bus import bus


def _event_spy():
    seen: list = []
    bus.subscribe("*", lambda e: seen.append(e))
    return seen


def _png_bytes(width: int = 96, height: int = 96, color: tuple = (200, 40, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


def _create_project(client: TestClient, name: str = "服装项目") -> dict:
    resp = client.post("/api/v1/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_chain(client: TestClient) -> dict[str, str]:
    project = _create_project(client)
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def _create_character(client: TestClient, project_id: str, name: str = "沈亦") -> dict:
    resp = client.post(f"/api/v1/projects/{project_id}/characters", json={"name": name})
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


# --- CRUD ------------------------------------------------------------------

def test_costume_crud_and_events(client: TestClient) -> None:
    seen = _event_spy()
    project = _create_project(client)

    created = client.post(
        f"/api/v1/projects/{project['id']}/costumes",
        json={"name": "校服", "description": "日常", "visual_prompt": "manga school uniform"},
    )
    assert created.status_code == 201
    body = created.json()
    costume_id = body["id"]
    assert body["name"] == "校服"
    assert body["revision"] == 1
    assert body["project_id"] == project["id"]

    # update
    updated = client.patch(
        f"/api/v1/costumes/{costume_id}",
        json={"revision": 1, "patch": {"description": "体育课"}},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "体育课"
    assert updated.json()["revision"] == 2

    # stale revision -> 409
    conflict = client.patch(
        f"/api/v1/costumes/{costume_id}",
        json={"revision": 1, "patch": {"description": "x"}},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"

    # list
    listed = client.get(f"/api/v1/projects/{project['id']}/costumes").json()
    assert [x["id"] for x in listed] == [costume_id]

    # soft delete
    deleted = client.delete(f"/api/v1/costumes/{costume_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/costumes/{costume_id}").status_code == 404

    assert len([e for e in seen if e.event_type == "costume.created"]) == 1
    assert len([e for e in seen if e.event_type == "costume.updated"]) == 1
    assert len([e for e in seen if e.event_type == "costume.deleted"]) == 1


def test_costume_validation(client: TestClient) -> None:
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    asset = _import_image(client, chain["project_id"])

    created = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "篮球队服", "character_id": char["id"], "reference_asset_id": asset},
    )
    assert created.status_code == 201
    assert created.json()["character_id"] == char["id"]
    assert created.json()["reference_asset_id"] == asset

    # unknown character -> 404
    resp = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "x", "character_id": "char_nope"},
    )
    assert resp.status_code == 404
    # unknown asset -> 404
    resp = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "x", "reference_asset_id": "asset_nope"},
    )
    assert resp.status_code == 404
    # cross-project asset -> 422
    other = _create_project(client, "其他项目")
    foreign_asset = _import_image(client, other["id"], (99, 99, 99))
    resp = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "x", "reference_asset_id": foreign_asset},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_costume_set_reference_asset_to_none(client: TestClient) -> None:
    """PATCH can clear reference_asset_id / character_id (explicit None)."""
    chain = _create_chain(client)
    asset = _import_image(client, chain["project_id"])
    created = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "比赛服", "reference_asset_id": asset},
    ).json()
    updated = client.patch(
        f"/api/v1/costumes/{created['id']}",
        json={"revision": 1, "patch": {"reference_asset_id": None}},
    )
    assert updated.status_code == 200
    assert updated.json()["reference_asset_id"] is None
    assert updated.json()["revision"] == 2


# --- shot_characters.costume_id -------------------------------------------

def test_shot_character_costume_extension(client: TestClient) -> None:
    """characters: [{character_id, costume_id}] records costume_id on link rows (P2-T010)."""
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    costume = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "校服", "character_id": char["id"]},
    ).json()
    costume_b = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "球服", "character_id": char["id"]},
    ).json()

    # create shot with the characters extension
    created = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={
            "shot_type": "medium",
            "characters": [
                {"character_id": char["id"], "costume_id": costume["id"]},
                {"character_id": char["id"], "costume_id": costume_b["id"]},
            ],
        },
    )
    # duplicate character_id violates the (shot_id, character_id) unique index -> reject
    assert created.status_code == 422, created.text

    # single character with costume
    created = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"shot_type": "medium", "characters": [{"character_id": char["id"], "costume_id": costume["id"]}]},
    )
    assert created.status_code == 201, created.text
    shot_id = created.json()["id"]
    assert created.json()["character_ids"] == [char["id"]]

    # verify link row has costume_id (assert via costume shot_count; the raw DB
    # column is covered by test_shot_characters_extension_records_costume_id_in_db)
    costume_read = client.get(f"/api/v1/costumes/{costume['id']}").json()
    assert costume_read["shot_count"] == 1

    # update shot with a different costume via characters extension
    updated = client.patch(
        f"/api/v1/shots/{shot_id}",
        json={
            "revision": 1,
            "patch": {"characters": [{"character_id": char["id"], "costume_id": costume_b["id"]}]},
        },
    )
    assert updated.status_code == 200, updated.text
    costume_b_read = client.get(f"/api/v1/costumes/{costume_b['id']}").json()
    assert costume_b_read["shot_count"] == 1
    costume_read = client.get(f"/api/v1/costumes/{costume['id']}").json()
    assert costume_read["shot_count"] == 0

    # unknown costume -> 404
    resp = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"shot_type": "medium", "characters": [{"character_id": char["id"], "costume_id": "costume_nope"}]},
    )
    assert resp.status_code == 404


def test_shot_characters_extension_records_costume_id_in_db(client: TestClient, db_path) -> None:
    """Verify the link row actually persists costume_id by inspecting the DB (semi-raw)."""
    chain = _create_chain(client)
    char = _create_character(client, chain["project_id"])
    costume = client.post(
        f"/api/v1/projects/{chain['project_id']}/costumes",
        json={"name": "校服", "character_id": char["id"]},
    ).json()

    created = client.post(
        f"/api/v1/scenes/{chain['scene_id']}/shots",
        json={"shot_type": "medium", "characters": [{"character_id": char["id"], "costume_id": costume["id"]}]},
    )
    assert created.status_code == 201, created.text
    shot_id = created.json()["id"]

    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT character_id, costume_id FROM shot_characters WHERE shot_id = :s"),
            {"s": shot_id},
        ).fetchone()
        assert row is not None
        assert row[0] == char["id"]
        assert row[1] == costume["id"]
    engine.dispose()
