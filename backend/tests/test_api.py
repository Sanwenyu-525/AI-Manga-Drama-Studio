"""API integration tests (mvp-spec §96): full CRUD chain through HTTP.

Covers the Stage A acceptance path:
Create Project → Create Episode → Create Scene → Create Shot → Modify Shot.
"""

from fastapi.testclient import TestClient


def create_chain(client: TestClient) -> dict[str, str]:
    project = client.post("/api/v1/projects", json={"name": "最后一种打法", "aspect_ratio": "9:16"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "第一集"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "体育馆", "mood": "tense"}).json()
    return {"project_id": project["id"], "episode_id": episode["id"], "scene_id": scene["id"]}


def test_health(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "healthy"


def test_project_crud(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Demo", "aspect_ratio": "16:9"}).json()
    assert created["status"] == "draft"
    assert created["aspect_ratio"] == "16:9"

    listed = client.get("/api/v1/projects").json()
    assert [p["id"] for p in listed] == [created["id"]]

    fetched = client.get(f"/api/v1/projects/{created['id']}")
    assert fetched.status_code == 200

    assert created["revision"] == 1
    updated = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"revision": 1, "patch": {"name": "Renamed"}},
    ).json()
    assert updated["name"] == "Renamed"
    assert updated["revision"] == 2

    missing = client.get("/api/v1/projects/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_episode_scene_shot_chain(client: TestClient) -> None:
    ids = create_chain(client)

    scenes = client.get(f"/api/v1/episodes/{ids['episode_id']}/scenes").json()
    assert len(scenes) == 1
    assert scenes[0]["scene_number"] == 1

    # auto shot numbering
    s1 = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "wide"}).json()
    s2 = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "close_up"}).json()
    assert s1["shot_number"] == 1 and s2["shot_number"] == 2
    assert s1["revision"] == 1 and s2["revision"] == 1

    shots = client.get(f"/api/v1/scenes/{ids['scene_id']}/shots").json()
    assert len(shots) == 2


def test_shot_update_bumps_revision_and_conflicts(client: TestClient) -> None:
    ids = create_chain(client)
    shot = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "medium"}).json()

    # valid optimistic update
    updated = client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": 1, "patch": {"shot_type": "close_up", "emotion": "tense"}},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["shot_type"] == "close_up"
    assert body["revision"] == 2
    assert body["dirty_state"] == "dirty_image"

    # stale revision → 409 conflict
    stale = client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": 1, "patch": {"duration": 5.0}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"

    # current revision still applies
    ok = client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": 2, "patch": {"duration": 5.0}},
    )
    assert ok.status_code == 200
    assert ok.json()["duration"] == 5.0


def test_storyboard_aggregate(client: TestClient) -> None:
    ids = create_chain(client)
    client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "wide", "duration": 3.0})
    client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "close_up", "duration": 2.5})

    sb = client.get(f"/api/v1/scenes/{ids['scene_id']}/storyboard").json()
    assert sb["scene"]["id"] == ids["scene_id"]
    assert len(sb["shots"]) == 2
    assert sb["shots"][0]["shot_number"] == 1
    assert sb["shots"][0]["status"] == "draft"
    assert sb["shots"][0]["thumbnail_url"] is None


def test_soft_delete(client: TestClient) -> None:
    ids = create_chain(client)
    shot = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "medium"}).json()

    deleted = client.delete(f"/api/v1/shots/{shot['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": shot["id"], "deleted": True}

    assert client.get(f"/api/v1/shots/{shot['id']}").status_code == 404
    assert len(client.get(f"/api/v1/scenes/{ids['scene_id']}/shots").json()) == 0

    # scene soft delete cascades visibility (shots filtered by scene existence)
    client.delete(f"/api/v1/scenes/{ids['scene_id']}")
    assert client.get(f"/api/v1/scenes/{ids['scene_id']}").status_code == 404


def test_reorder_shots(client: TestClient) -> None:
    ids = create_chain(client)
    s1 = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "wide"}).json()
    s2 = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "medium"}).json()
    s3 = client.post(f"/api/v1/scenes/{ids['scene_id']}/shots", json={"shot_type": "close_up"}).json()

    reordered = client.patch(
        f"/api/v1/scenes/{ids['scene_id']}/shots/reorder",
        json=[s3["id"], s1["id"], s2["id"]],
    ).json()
    assert [s["shot_number"] for s in reordered] == [1, 2, 3]
    assert [s["id"] for s in reordered] == [s3["id"], s1["id"], s2["id"]]
