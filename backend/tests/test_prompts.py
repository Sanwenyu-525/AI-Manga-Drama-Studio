"""ADR-002: prompt versioning — PromptService + API + shot cache sync + generation provenance."""

import asyncio

from fastapi.testclient import TestClient

from app.generations.worker import run_generation


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _chain(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "PromptV"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, night city"},
    ).json()
    return {"project": project, "episode": episode, "scene": scene, "shot": shot}


def test_shot_create_backs_inline_prompt_with_v1(client: TestClient) -> None:
    c = _chain(client)
    shot = c["shot"]
    # prompt row exists with v1 and the shot pointer is wired
    prompts = client.get(f"/api/v1/shots/{shot['id']}/prompts").json()
    assert len(prompts) == 1
    p = prompts[0]
    assert p["prompt_type"] == "SHOT_IMAGE"
    assert p["versions_count"] == 1
    versions = client.get(f"/api/v1/prompts/{p['id']}/versions").json()
    assert versions[0]["version_number"] == 1
    assert versions[0]["positive_prompt"] == "manga style, night city"
    assert versions[0]["is_active"] is True
    # deprecated cache is in sync
    shot_after = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert shot_after["image_prompt"] == "manga style, night city"


def test_shot_update_creates_new_prompt_version(client: TestClient) -> None:
    c = _chain(client)
    shot = c["shot"]
    revision = shot["revision"]

    resp = client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": revision, "patch": {"image_prompt": "manga style, dawn"}},
    )
    assert resp.status_code == 200

    prompts = client.get(f"/api/v1/shots/{shot['id']}/prompts").json()
    assert prompts[0]["versions_count"] == 2
    versions = client.get(f"/api/v1/prompts/{prompts[0]['id']}/versions").json()
    assert [v["version_number"] for v in versions] == [2, 1]
    assert versions[0]["is_active"] is True  # newest active
    assert versions[0]["positive_prompt"] == "manga style, dawn"

    # cache synced + revision bumped
    shot_after = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert shot_after["image_prompt"] == "manga style, dawn"
    assert shot_after["revision"] == revision + 1


def test_activate_old_prompt_version_switches_pointer(client: TestClient) -> None:
    c = _chain(client)
    shot = c["shot"]
    client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": shot["revision"], "patch": {"image_prompt": "v2 prompt"}},
    )
    prompts = client.get(f"/api/v1/shots/{shot['id']}/prompts").json()
    prompt_id = prompts[0]["id"]
    versions = client.get(f"/api/v1/prompts/{prompt_id}/versions").json()
    v1 = versions[1]  # older

    activated = client.post(f"/api/v1/prompts/{prompt_id}/versions/{v1['id']}/activate").json()
    assert activated["is_active"] is True
    assert activated["positive_prompt"] == "manga style, night city"

    shot_after = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert shot_after["image_prompt"] == "manga style, night city"  # cache follows active


def test_generation_records_prompt_version_id(client: TestClient) -> None:
    c = _chain(client)
    shot = c["shot"]
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    assert created["prompt_version_id"] is not None
    _drive(created["id"])

    done = client.get(f"/api/v1/generations/{created['id']}").json()
    assert done["status"] == "completed"
    assert done["prompt_version_id"] == created["prompt_version_id"]


def test_manual_prompt_version_apis(client: TestClient) -> None:
    c = _chain(client)
    shot = c["shot"]
    # create a video prompt row via API
    created = client.post(
        f"/api/v1/shots/{shot['id']}/prompts",
        json={"prompt_type": "SHOT_VIDEO", "positive_prompt": "camera push-in"},
    )
    assert created.status_code == 201
    assert created.json()["version_number"] == 1

    prompts = client.get(f"/api/v1/shots/{shot['id']}/prompts").json()
    types = {p["prompt_type"] for p in prompts}
    assert types == {"SHOT_IMAGE", "SHOT_VIDEO"}

    video_prompt = next(p for p in prompts if p["prompt_type"] == "SHOT_VIDEO")
    v2 = client.post(
        f"/api/v1/prompts/{video_prompt['id']}/versions",
        json={"positive_prompt": "camera push-in, closer"},
    )
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2
