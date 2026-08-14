"""Stage C tests: generation chain (mvp-spec 搂75) with MockImageProvider.

Create generation (202) 鈫?worker completes 鈫?Asset + MediaVersion + shot active version
鈫?regenerate gives V2 while V1 stays 鈫?retry/cancel 鈫?versions list & activate.

NOTE: TestClient's portal event loop does not advance timers between requests, so the
background worker poll would never run here. Tests drive `run_generation` directly
(the worker loop itself is verified in production/uvicorn; core logic lives in run_generation).
"""

import asyncio
import time

from fastapi.testclient import TestClient

from app.generations.worker import run_generation


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _wait_status(client: TestClient, generation_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"generation {generation_id} did not finish in {timeout}s")


def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "StageC"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, city night"},
    ).json()
    return shot


def test_generation_chain_completes(client: TestClient) -> None:
    shot = _make_shot(client)

    resp = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert resp.status_code == 202
    created = resp.json()
    assert created["status"] == "queued"
    assert created["shot_id"] == shot["id"]

    _drive(created["id"])
    done = _wait_status(client, created["id"])
    assert done["status"] == "completed", done.get("error_message")
    assert done["progress"] == 100
    assert done["output_asset_id"]

    # asset exists and serves content
    asset = client.get(f"/api/v1/assets/{done['output_asset_id']}/content")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "image/png"

    # shot got active version + thumbnail in storyboard
    storyboard = client.get(f"/api/v1/scenes/{shot['scene_id']}/storyboard").json()
    summary = storyboard["shots"][0]
    assert summary["thumbnail_url"] is not None

    # version row exists and is active
    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["is_active"] is True


def test_regenerate_preserves_v1(client: TestClient) -> None:
    shot = _make_shot(client)
    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(g1["id"]); _wait_status(client, g1["id"])

    g2 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(g2["id"])
    done2 = _wait_status(client, g2["id"])
    assert done2["status"] == "completed"

    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    assert [v["version_number"] for v in versions] == [2, 1]
    assert versions[0]["is_active"] is True  # V2 active
    assert versions[1]["is_active"] is False  # V1 preserved, not active

    # thumbnails differ (different generation)
    storyboard = client.get(f"/api/v1/scenes/{shot['scene_id']}/storyboard").json()
    assert storyboard["shots"][0]["thumbnail_url"] == f"/api/v1/assets/{done2['output_asset_id']}/thumbnail"


def test_activate_old_version(client: TestClient) -> None:
    shot = _make_shot(client)
    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(g1["id"]); _wait_status(client, g1["id"])
    g2 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(g2["id"])
    done2 = _wait_status(client, g2["id"])

    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    v1 = versions[1]  # older

    activated = client.post(f"/api/v1/media-versions/{v1['id']}/activate").json()
    assert activated["is_active"] is True

    versions_after = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    by_number = {v["version_number"]: v["is_active"] for v in versions_after}
    assert by_number[1] is True
    assert by_number[2] is False

    # storyboard now points at V1's asset
    storyboard = client.get(f"/api/v1/scenes/{shot['scene_id']}/storyboard").json()
    assert storyboard["shots"][0]["thumbnail_url"] == f"/api/v1/assets/{v1['asset_id']}/thumbnail"


def test_generation_retry_creates_new_record(client: TestClient) -> None:
    shot = _make_shot(client)
    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(g1["id"]); _wait_status(client, g1["id"])

    retried = client.post(f"/api/v1/generations/{g1['id']}/retry")
    assert retried.status_code == 202
    body = retried.json()
    assert body["id"] != g1["id"]
    assert body["retry_of"] == g1["id"]

    _drive(body["id"])
    done = _wait_status(client, body["id"])
    assert done["status"] == "completed"

    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    assert len(versions) == 2  # original + retry


def test_generation_cancel(client: TestClient) -> None:
    shot = _make_shot(client)
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()

    # cancel right away (mock is fast, but cancel before completion is best-effort)
    cancelled = client.post(f"/api/v1/generations/{created['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    assert versions == []  # cancelled generation produced nothing

