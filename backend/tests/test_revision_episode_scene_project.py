"""P1: revision optimistic locking for Episode/Scene/Project + ProjectSettings API.

Covers:
- Double-writer with the same revision: exactly one wins, the other gets 409.
- Successful updates bump revision by 1.
- GET/PUT /projects/{id}/settings round-trip (partial update preserves others).
"""

from fastapi.testclient import TestClient


def _project(client: TestClient) -> dict:
    return client.post("/api/v1/projects", json={"name": "rev-proj"}).json()


def _chain(client: TestClient) -> dict:
    project = _project(client)
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    return {"project": project, "episode": episode, "scene": scene}


# --- double-writer: same revision only one succeeds, other 409 ---


def test_project_double_writer_same_revision_one_conflict(client: TestClient) -> None:
    p = _project(client)
    assert p["revision"] == 1

    # both writers read revision=1
    ok = client.patch(
        f"/api/v1/projects/{p['id']}",
        json={"revision": 1, "patch": {"name": "writer-a"}},
    )
    assert ok.status_code == 200
    assert ok.json()["revision"] == 2

    stale = client.patch(
        f"/api/v1/projects/{p['id']}",
        json={"revision": 1, "patch": {"name": "writer-b"}},
    )
    assert stale.status_code == 409
    err = stale.json()["error"]
    assert err["code"] == "CONFLICT"
    assert err["details"]["expected_revision"] == 1
    assert err["details"]["current_revision"] == 2

    # the survivor's name is preserved
    assert client.get(f"/api/v1/projects/{p['id']}").json()["name"] == "writer-a"


def test_episode_double_writer_same_revision_one_conflict(client: TestClient) -> None:
    c = _chain(client)
    ep = c["episode"]
    assert ep["revision"] == 1

    ok = client.patch(
        f"/api/v1/episodes/{ep['id']}",
        json={"revision": 1, "patch": {"title": "writer-a"}},
    )
    assert ok.status_code == 200
    assert ok.json()["revision"] == 2

    stale = client.patch(
        f"/api/v1/episodes/{ep['id']}",
        json={"revision": 1, "patch": {"title": "writer-b"}},
    )
    assert stale.status_code == 409
    err = stale.json()["error"]
    assert err["code"] == "CONFLICT"
    assert err["details"]["expected_revision"] == 1
    assert err["details"]["current_revision"] == 2

    assert client.get(f"/api/v1/episodes/{ep['id']}").json()["title"] == "writer-a"


def test_scene_double_writer_same_revision_one_conflict(client: TestClient) -> None:
    c = _chain(client)
    scene = c["scene"]
    assert scene["revision"] == 1

    ok = client.patch(
        f"/api/v1/scenes/{scene['id']}",
        json={"revision": 1, "patch": {"name": "writer-a"}},
    )
    assert ok.status_code == 200
    assert ok.json()["revision"] == 2

    stale = client.patch(
        f"/api/v1/scenes/{scene['id']}",
        json={"revision": 1, "patch": {"name": "writer-b"}},
    )
    assert stale.status_code == 409
    err = stale.json()["error"]
    assert err["code"] == "CONFLICT"
    assert err["details"]["expected_revision"] == 1
    assert err["details"]["current_revision"] == 2

    assert client.get(f"/api/v1/scenes/{scene['id']}").json()["name"] == "writer-a"


# --- revision bumps (single writer, sequential) ---


def test_episode_scene_revision_bumps_sequentially(client: TestClient) -> None:
    c = _chain(client)
    ep, scene = c["episode"], c["scene"]
    assert ep["revision"] == 1 and scene["revision"] == 1

    ep2 = client.patch(
        f"/api/v1/episodes/{ep['id']}",
        json={"revision": 1, "patch": {"status": "analyzed"}},
    ).json()
    assert ep2["revision"] == 2

    ep3 = client.patch(
        f"/api/v1/episodes/{ep['id']}",
        json={"revision": 2, "patch": {"summary": "done"}},
    ).json()
    assert ep3["revision"] == 3

    s2 = client.patch(
        f"/api/v1/scenes/{scene['id']}",
        json={"revision": 1, "patch": {"status": "planned"}},
    ).json()
    assert s2["revision"] == 2


def test_missing_revision_is_422(client: TestClient) -> None:
    p = _project(client)
    # PATCH body must be {revision, patch}; a bare patch is rejected (422), not silently
    # applied — the API contract forbids unguarded writes.
    resp = client.patch(f"/api/v1/projects/{p['id']}", json={"name": "no-rev"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"


# --- ProjectSettings GET/PUT round-trip ---


def test_settings_get_returns_defaults_on_create(client: TestClient) -> None:
    p = _project(client)
    resp = client.get(f"/api/v1/projects/{p['id']}/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == p["id"]
    assert body["language"] == "zh-CN"
    assert body["auto_retry"] == 1
    assert body["max_retry_count"] == 3
    assert body["auto_save"] == 1
    assert body["continuity_enabled"] == 1
    assert body["auto_activate_new_generation"] == 0


def test_settings_put_partial_update_preserves_others(client: TestClient) -> None:
    p = _project(client)
    put = client.put(
        f"/api/v1/projects/{p['id']}/settings",
        json={"language": "en-US", "default_image_provider": "mock", "max_retry_count": 5},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["language"] == "en-US"
    assert body["default_image_provider"] == "mock"
    assert body["max_retry_count"] == 5
    # unprovided fields keep their default/no-change value
    assert body["auto_retry"] == 1
    assert body["continuity_enabled"] == 1
    assert body["default_llm_provider"] is None

    # GET reflects the PUT
    got = client.get(f"/api/v1/projects/{p['id']}/settings").json()
    assert got["language"] == "en-US"
    assert got["max_retry_count"] == 5
    assert got["default_image_provider"] == "mock"


def test_settings_json_unknown_keys_roundtrip(client: TestClient) -> None:
    p = _project(client)
    put = client.put(
        f"/api/v1/projects/{p['id']}/settings",
        json={"settings_json": {"customKey": {"nested": True}, "brand": "studio"}},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["settings_json"] == {"customKey": {"nested": True}, "brand": "studio"}

    # unknown keys are merged with previously stored settings_json
    put2 = client.put(
        f"/api/v1/projects/{p['id']}/settings",
        json={"settings_json": {"brand": "new-studio", "extra": 1}},
    )
    assert put2.status_code == 200
    assert put2.json()["settings_json"] == {
        "customKey": {"nested": True},
        "brand": "new-studio",
        "extra": 1,
    }


def test_settings_404_for_missing_project(client: TestClient) -> None:
    resp = client.get("/api/v1/projects/does-not-exist/settings")
    assert resp.status_code == 404
