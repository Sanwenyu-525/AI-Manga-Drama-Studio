"""Episode + Scene CRUD (delete) API tests."""

from fastapi.testclient import TestClient


def _chain(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "CRUD 测试"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "第 1 集"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "场景 A"}).json()
    shot = client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "wide"}).json()
    return {"project": project, "episode": episode, "scene": scene, "shot": shot}


def test_episode_rename(client: TestClient) -> None:
    c = _chain(client)
    resp = client.patch(f"/api/v1/episodes/{c['episode']['id']}", json={"title": "改名集"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "改名集"


def test_episode_delete_cascade(client: TestClient) -> None:
    c = _chain(client)
    resp = client.delete(f"/api/v1/episodes/{c['episode']['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert client.get(f"/api/v1/episodes/{c['episode']['id']}").status_code == 404
    # scenes of the deleted episode are gone too
    assert client.get(f"/api/v1/scenes/{c['scene']['id']}").status_code == 404
    assert client.get(f"/api/v1/episodes/{c['episode']['id']}/scenes").status_code == 404


def test_scene_rename(client: TestClient) -> None:
    c = _chain(client)
    resp = client.patch(f"/api/v1/scenes/{c['scene']['id']}", json={"name": "改名场景"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名场景"


def test_scene_delete(client: TestClient) -> None:
    c = _chain(client)
    resp = client.delete(f"/api/v1/scenes/{c['scene']['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert client.get(f"/api/v1/scenes/{c['scene']['id']}").status_code == 404
    # storyboard of the deleted scene is gone
    assert client.get(f"/api/v1/scenes/{c['scene']['id']}/storyboard").status_code == 404
