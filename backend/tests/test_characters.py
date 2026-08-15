"""Character Management tests (mvp-spec §105-BE, database-v0.1 §7/§11).

Covers the P1 acceptance path:
- Character CRUD with revision optimistic concurrency + soft delete
- Shot <-> Character assignment via the shot_characters link table
- Project bootstrap returning characters/episodes/providers summaries
"""

from fastapi.testclient import TestClient


def create_project(client: TestClient, name: str = "最后一种打法") -> dict:
    return client.post("/api/v1/projects", json={"name": name, "aspect_ratio": "9:16"}).json()


def create_chain(client: TestClient) -> dict[str, str]:
    project = create_project(client)
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "第一集"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "体育馆"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def create_character(client: TestClient, project_id: str, name: str = "沈亦") -> dict:
    resp = client.post(
        f"/api/v1/projects/{project_id}/characters",
        json={"name": name, "alias": "Shen", "gender": "female", "appearance": "黑色长发"},
    )
    assert resp.status_code == 201
    return resp.json()


def test_character_crud_with_revision_and_soft_delete(client: TestClient) -> None:
    project = create_project(client)
    character = create_character(client, project["id"])

    fetched = client.get(f"/api/v1/characters/{character['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["name"] == "沈亦"
    assert body["alias"] == "Shen"
    assert body["revision"] == 1
    assert body["shot_count"] == 0

    listed = client.get(f"/api/v1/projects/{project['id']}/characters").json()
    assert [c["id"] for c in listed] == [character["id"]]

    updated = client.patch(
        f"/api/v1/characters/{character['id']}",
        json={"revision": 1, "patch": {"name": "沈亦（成年）", "personality": "外冷内热"}},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "沈亦（成年）"
    assert body["personality"] == "外冷内热"
    assert body["revision"] == 2

    stale = client.patch(
        f"/api/v1/characters/{character['id']}",
        json={"revision": 1, "patch": {"gender": "male"}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"

    deleted = client.delete(f"/api/v1/characters/{character['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": character["id"], "deleted": True}
    assert client.get(f"/api/v1/characters/{character['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/characters").json() == []


def test_shot_character_assignment_roundtrip(client: TestClient) -> None:
    ids = create_chain(client)
    shen = create_character(client, ids["project_id"], "沈亦")
    gu = create_character(client, ids["project_id"], "顾言")

    shot = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots",
        json={"shot_type": "medium", "character_ids": [shen["id"], gu["id"]]},
    )
    assert shot.status_code == 201
    shot_id = shot.json()["id"]
    assert shot.json()["character_ids"] == [shen["id"], gu["id"]]

    storyboard = client.get(f"/api/v1/scenes/{ids['scene_id']}/storyboard").json()
    assert storyboard["shots"][0]["character_names"] == ["沈亦", "顾言"]

    fetched = client.get(f"/api/v1/shots/{shot_id}").json()
    assert fetched["character_ids"] == [shen["id"], gu["id"]]

    replaced = client.patch(
        f"/api/v1/shots/{shot_id}",
        json={"revision": 1, "patch": {"character_ids": [gu["id"]]}},
    )
    assert replaced.status_code == 200
    body = replaced.json()
    assert body["character_ids"] == [gu["id"]]
    assert body["revision"] == 2
    assert body["dirty_state"] == "dirty_image"

    storyboard2 = client.get(f"/api/v1/scenes/{ids['scene_id']}/storyboard").json()
    assert storyboard2["shots"][0]["character_names"] == ["顾言"]

    gu_read = client.get(f"/api/v1/characters/{gu['id']}").json()
    assert gu_read["shot_count"] == 1
    shen_read = client.get(f"/api/v1/characters/{shen['id']}").json()
    assert shen_read["shot_count"] == 0


def test_shot_character_validation(client: TestClient) -> None:
    ids = create_chain(client)
    other_project = create_project(client, "另一个项目")
    foreign = create_character(client, other_project["id"], "别家角色")

    resp = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots",
        json={"shot_type": "medium", "character_ids": ["character_does_not_exist"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    resp = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots",
        json={"shot_type": "medium", "character_ids": [foreign["id"]]},
    )
    assert resp.status_code == 422  # errors.py: VALIDATION_ERROR → 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_bootstrap_returns_summaries(client: TestClient) -> None:
    ids = create_chain(client)
    create_character(client, ids["project_id"], "沈亦")

    resp = client.get(f"/api/v1/projects/{ids['project_id']}/bootstrap")
    assert resp.status_code == 200
    body = resp.json()

    assert body["project"]["id"] == ids["project_id"]
    assert len(body["episodes"]) == 1
    assert body["episodes"][0]["id"] == ids["episode_id"]
    assert body["episodes"][0]["scene_count"] == 1
    assert [c["name"] for c in body["characters"]] == ["沈亦"]
    assert isinstance(body["providers"], list) and len(body["providers"]) >= 2
    assert body["active_generations"] == 0
    assert body["active_agent_runs"] == 0

    assert client.get("/api/v1/projects/does-not-exist/bootstrap").status_code == 404
