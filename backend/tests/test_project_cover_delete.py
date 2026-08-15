"""Project cover upload + project delete API tests."""

from fastapi.testclient import TestClient

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # minimal PNG header + padding


def _make_project(client: TestClient) -> dict:
    return client.post("/api/v1/projects", json={"name": "封面测试项目"}).json()


def test_cover_upload_and_read(client: TestClient) -> None:
    project = _make_project(client)
    assert project["cover_url"] is None

    resp = client.post(
        f"/api/v1/projects/{project['id']}/cover",
        files={"file": ("cover.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cover_url"] == f"/api/v1/projects/{project['id']}/cover"

    fetched = client.get(f"/api/v1/projects/{project['id']}")
    assert fetched.json()["cover_url"] == body["cover_url"]

    cover = client.get(f"/api/v1/projects/{project['id']}/cover")
    assert cover.status_code == 200
    assert cover.content.startswith(b"\x89PNG")

    # replace cover → still readable
    resp2 = client.post(
        f"/api/v1/projects/{project['id']}/cover",
        files={"file": ("new.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")},
    )
    assert resp2.status_code == 200
    cover2 = client.get(f"/api/v1/projects/{project['id']}/cover")
    assert cover2.content.startswith(b"\xff\xd8\xff\xe0")


def test_cover_unsupported_format(client: TestClient) -> None:
    project = _make_project(client)
    resp = client.post(
        f"/api/v1/projects/{project['id']}/cover",
        files={"file": ("cover.exe", b"MZ" * 16, "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cover_missing_404(client: TestClient) -> None:
    project = _make_project(client)
    resp = client.get(f"/api/v1/projects/{project['id']}/cover")
    assert resp.status_code == 404


def test_delete_project_cascade(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "待删除项目"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "第 1 集"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "场景"}).json()
    client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "medium"})

    resp = client.delete(f"/api/v1/projects/{project['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # project gone from list + direct fetch 404
    ids = [p["id"] for p in client.get("/api/v1/projects").json()]
    assert project["id"] not in ids
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404

    # cascade: the whole tree is soft-deleted — project fetch and episode sub-resources are gone
    assert client.get(f"/api/v1/projects/{project['id']}/episodes").status_code == 404
    assert client.get(f"/api/v1/episodes/{episode['id']}/scenes").status_code == 404
