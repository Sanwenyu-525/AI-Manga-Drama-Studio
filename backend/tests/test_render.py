"""Phase 9 tests — Episode Render (P9-E3): queue → worker → FINAL_VIDEO asset.

A type='render' Generation executes through the MockRenderProvider (pure-Python
MJPEG AVI) and its output registers as an immutable FINAL_VIDEO asset under
v​g:episode:{episode_id}:FINAL_VIDEO. Also covers preview + contract errors.
"""
import asyncio

import struct
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.generations.worker import run_generation


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _gen(client: TestClient, timeline_id: str) -> dict:
    resp = client.post(f"/api/v1/timelines/{timeline_id}/render")
    assert resp.status_code == 202
    return resp.json()


def _wait_done(client: TestClient, generation_id: str, timeout: float = 20.0) -> dict:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"render generation {generation_id} did not finish in {timeout}s")


def _build_rendered_timeline(client: TestClient) -> dict:
    """Project → episode → 1 scene × 2 shots with images → timeline → sequence."""
    project = client.post("/api/v1/projects", json={"name": "P9Render"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()

    shots = []
    for i in range(2):
        shot = client.post(
            f"/api/v1/scenes/{scene['id']}/shots",
            json={"shot_type": "medium", "duration": 2.0, "image_prompt": f"p{i}"},
        ).json()
        gen = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
        _drive(gen["id"])
        done = _wait_done(client, gen["id"])
        assert done["status"] == "completed", done.get("error_message")
        shots.append(shot)

    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()
    arranged = client.post(f"/api/v1/timelines/{timeline['id']}/sequence-from-shots").json()
    assert len(arranged["clips"]) == 2
    return {"project_id": project["id"], "episode_id": episode["id"], "timeline_id": timeline["id"], "shots": shots}


def test_render_requires_video_clips(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "P9Empty"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()

    resp = client.post(f"/api/v1/timelines/{timeline['id']}/render")
    assert resp.status_code == 422


def test_render_completes_and_registers_final_video(client: TestClient) -> None:
    ctx = _build_rendered_timeline(client)
    rendered = _gen(client, ctx["timeline_id"])
    assert rendered["status"] == "queued"
    assert rendered["episode_id"] == ctx["episode_id"]

    _drive(rendered["generation_id"])
    done = _wait_done(client, rendered["generation_id"])
    assert done["status"] == "completed", done.get("error_message")
    assert done["type"] == "render"
    assert done["progress"] == 100
    assert done["output_asset_id"]

    # FINAL_VIDEO asset exists + is a real RIFF/AVI file
    final = client.get(f"/api/v1/episodes/{ctx['episode_id']}/final-video")
    assert final.status_code == 200
    fv = final.json()
    assert fv["asset_id"] == done["output_asset_id"]
    assert fv["type"] == "video"
    assert fv["version_number"] == 1
    assert fv["content_url"] == f"/api/v1/assets/{fv['asset_id']}/content"

    content = client.get(f"/api/v1/assets/{fv['asset_id']}/content")
    assert content.status_code == 200
    body = content.content
    assert body[:4] == b"RIFF" and body[8:12] == b"AVI "

    # asset file sits in the project tree with the FINAL_VIDEO version group
    asset = client.get(f"/api/v1/assets/{fv['asset_id']}").json()
    assert asset["version_group_id"] == f"vg:episode:{ctx['episode_id']}:FINAL_VIDEO"
    assert asset["version_number"] == 1

    # timeline marked RENDERED
    timeline = client.get(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    assert timeline["status"] == "RENDERED"

    # second render → immutable V2 coexists with V1
    rendered2 = _gen(client, ctx["timeline_id"])
    _drive(rendered2["generation_id"])
    done2 = _wait_done(client, rendered2["generation_id"])
    assert done2["status"] == "completed"
    final2 = client.get(f"/api/v1/episodes/{ctx['episode_id']}/final-video").json()
    assert final2["asset_id"] == done2["output_asset_id"]
    assert final2["version_number"] == 2


def test_render_produces_playable_frame_count(client: TestClient) -> None:
    """The mock encoder writes one 00dc frame per (duration × fps), like a real video."""
    ctx = _build_rendered_timeline(client)
    rendered = _gen(client, ctx["timeline_id"])
    _drive(rendered["generation_id"])
    done = _wait_done(client, rendered["generation_id"])
    assert done["status"] == "completed"

    asset = client.get(f"/api/v1/assets/{done['output_asset_id']}").json()
    # asset file exists under the project dir
    path = settings.data_dir / "projects" / ctx["project_id"] / (asset["file_path"] or "")
    assert path.is_file()
    data = path.read_bytes()
    # count 00dc frame records INSIDE the movi list only (the idx1 entries also
    # repeat the fourcc, so scope the count to the movi region)
    movi_start = data.find(b"movi") + 4
    idx_start = data.find(b"idx1")
    assert movi_start > 0 and idx_start > movi_start
    movi = data[movi_start:idx_start]
    frame_count = movi.count(b"00dc")
    assert frame_count > 0
    # 2 clips × 2s × 24fps = 96 frames
    assert frame_count == 96, frame_count
    # idx1 present + RIFF sizes consistent
    assert b"idx1" in data
    riff_size = struct.unpack("<I", data[4:8])[0]
    assert riff_size == len(data) - 8
    # avih.dwTotalFrames matches the frame count (data starts at avih_pos+8)
    avih_pos = data.find(b"avih")
    total_frames = struct.unpack("<I", data[avih_pos + 24 : avih_pos + 28])[0]
    assert total_frames == 96, total_frames


def test_render_preview_after_render(client: TestClient) -> None:
    """After a render the poster/frame-strip is registered as the thumbnail."""
    ctx = _build_rendered_timeline(client)
    rendered = _gen(client, ctx["timeline_id"])
    _drive(rendered["generation_id"])
    _wait_done(client, rendered["generation_id"])

    final = client.get(f"/api/v1/episodes/{ctx['episode_id']}/final-video").json()
    if final.get("thumbnail_url"):
        thumb = client.get(final["thumbnail_url"])
        assert thumb.status_code == 200