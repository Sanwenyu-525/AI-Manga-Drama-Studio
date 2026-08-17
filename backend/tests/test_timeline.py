"""Phase 9 tests — Timeline domain + API (P9-E1/E2).

Timeline (per episode) → tracks (VIDEO/VOICE/MUSIC/SUBTITLE) → clips (Timeline
Items bound to a specific asset version). Covers CRUD, version replace,
one-click sequence-from-shots, preview, and the contract errors.
"""

import asyncio
import time

from fastapi.testclient import TestClient

from app.generations.worker import run_generation

DEFAULT_TRACK_TYPES = ("VIDEO", "VOICE", "MUSIC", "SUBTITLE")


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


def build_episode_with_shot_images(client: TestClient, *, shots: int | None = None) -> dict:
    """Project → episode → 2 scenes × N shots, each with a generated image asset
    (active_image_asset_id set) so sequence-from-shots has sources."""
    project = client.post("/api/v1/projects", json={"name": "P9"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene1 = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    scene2 = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S2"}).json()

    result: dict = {"project_id": project["id"], "episode_id": episode["id"], "shots": []}
    for scene in (scene1, scene2):
        count = shots if shots is not None else 2
        for i in range(count):
            shot = client.post(
                f"/api/v1/scenes/{scene['id']}/shots",
                json={
                    "shot_type": "medium",
                    "duration": 3.0,
                    "dialogue": f"line {scene['scene_number']}-{i + 1}" if i % 2 == 0 else None,
                    "image_prompt": f"manga {scene['scene_number']}-{i + 1}",
                },
            ).json()
            gen = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
            _drive(gen["id"])
            done = _wait_status(client, gen["id"])
            assert done["status"] == "completed", done.get("error_message")
            result["shots"].append(shot)
    return result


def _active_image(client: TestClient, shot_id: str) -> str:
    versions = client.get(f"/api/v1/shots/{shot_id}/image-versions").json()
    active = next(v for v in versions if v["is_active"])
    return active["asset_id"]


def _video_track_id(timeline: dict) -> str:
    return next(t["id"] for t in timeline["tracks"] if t["track_type"] == "VIDEO")


def _subtitle_track_id(timeline: dict) -> str:
    return next(t["id"] for t in timeline["tracks"] if t["track_type"] == "SUBTITLE")


def test_timeline_create_with_default_tracks_and_get(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client)

    # 404 before creation
    assert client.get(f"/api/v1/episodes/{ctx['episode_id']}/timeline").status_code == 404

    created = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline")
    assert created.status_code == 201
    timeline = created.json()
    assert timeline["episode_id"] == ctx["episode_id"]
    assert timeline["status"] == "DRAFT"
    assert [t["track_type"] for t in timeline["tracks"]] == list(DEFAULT_TRACK_TYPES)
    assert timeline["clips"] == []

    # duplicate creation → 422
    again = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline")
    assert again.status_code == 422

    fetched = client.get(f"/api/v1/episodes/{ctx['episode_id']}/timeline")
    assert fetched.status_code == 200
    assert len(fetched.json()["tracks"]) == 4


def test_clip_crud_and_edit(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client)
    timeline = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    video_track = _video_track_id(timeline)
    asset_id = _active_image(client, ctx["shots"][0]["id"])

    clip = client.post(
        f"/api/v1/timelines/{timeline['id']}/clips",
        json={"track_id": video_track, "asset_id": asset_id, "start_time": 0, "end_time": 3},
    )
    assert clip.status_code == 201
    body = clip.json()
    assert body["start_time"] == 0 and body["end_time"] == 3
    assert body["asset"]["id"] == asset_id

    # move + trim via PATCH (the drag/trim persistence contract)
    moved = client.patch(
        f"/api/v1/timeline-clips/{body['id']}",
        json={"patch": {"start_time": 1.5, "end_time": 4.5}},
    )
    assert moved.status_code == 200
    mv = moved.json()
    assert mv["start_time"] == 1.5 and mv["end_time"] == 4.5

    # trim edges
    trim = client.patch(
        f"/api/v1/timeline-clips/{body['id']}",
        json={"patch": {"end_time": 4.0, "source_in": 0.5, "source_out": 2.5}},
    ).json()
    assert trim["end_time"] == 4.0 and trim["source_in"] == 0.5 and trim["source_out"] == 2.5

    # disable/enable
    off = client.patch(f"/api/v1/timeline-clips/{body['id']}", json={"patch": {"enabled": 0}}).json()
    assert off["enabled"] == 0

    # delete
    deleted = client.delete(f"/api/v1/timeline-clips/{body['id']}")
    assert deleted.status_code == 200
    assert client.delete(f"/api/v1/timeline-clips/{body['id']}").status_code == 404


def test_clip_validation_errors(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client)
    timeline = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    video_track = _video_track_id(timeline)
    asset_id = _active_image(client, ctx["shots"][0]["id"])

    # end_time <= start_time → 422
    bad = client.post(
        f"/api/v1/timelines/{timeline['id']}/clips",
        json={"track_id": video_track, "asset_id": asset_id, "start_time": 3, "end_time": 3},
    )
    assert bad.status_code == 422

    # unknown track → 422
    bad_track = client.post(
        f"/api/v1/timelines/{timeline['id']}/clips",
        json={"track_id": "nope", "asset_id": asset_id, "start_time": 0, "end_time": 1},
    )
    assert bad_track.status_code == 422

    # asset not in the project → 422
    bad_asset = client.post(
        f"/api/v1/timelines/{timeline['id']}/clips",
        json={"track_id": video_track, "asset_id": "definitely-missing", "start_time": 0, "end_time": 1},
    )
    assert bad_asset.status_code == 422


def test_replace_clip_asset_version(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client)
    timeline = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    video_track = _video_track_id(timeline)
    asset_1 = _active_image(client, ctx["shots"][0]["id"])
    asset_2 = _active_image(client, ctx["shots"][1]["id"])

    clip = client.post(
        f"/api/v1/timelines/{timeline['id']}/clips",
        json={"track_id": video_track, "asset_id": asset_1, "start_time": 0, "end_time": 3},
    ).json()

    replaced = client.post(
        f"/api/v1/timeline-clips/{clip['id']}/replace-asset", json={"asset_id": asset_2}
    )
    assert replaced.status_code == 200
    assert replaced.json()["asset_id"] == asset_2
    assert replaced.json()["asset"]["id"] == asset_2


def test_sequence_from_shots_arranges_video_and_subtitle(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client, shots=2)  # 2 scenes × 2 shots
    timeline = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    video_track = _video_track_id(timeline)

    arranged = client.post(f"/api/v1/timelines/{timeline['id']}/sequence-from-shots")
    assert arranged.status_code == 200
    data = arranged.json()

    video_clips = [c for c in data["clips"] if c["track_id"] == video_track]
    assert len(video_clips) == 4  # one per shot (all got images)
    # back-to-back at 3s each → 0..3, 3..6, 6..9, 9..12
    assert video_clips[0]["start_time"] == 0 and video_clips[0]["end_time"] == 3
    assert video_clips[3]["start_time"] == 9 and video_clips[3]["end_time"] == 12
    assert data["duration"] == 12.0
    # each video clip bound to its shot's active image asset
    shot_asset = {s["id"]: _active_image(client, s["id"]) for s in ctx["shots"]}
    for clip in video_clips:
        assert clip["asset_id"] == shot_asset[clip["shot_id"]]
        assert clip["shot_id"] is not None

    subtitle_track = _subtitle_track_id(data)
    subs = [c for c in data["clips"] if c["track_id"] == subtitle_track]
    assert len(subs) == 2  # dialogue on i%2==0 shots (2 of 4)
    assert all(c["text"] for c in subs)

    # idempotent: re-running replaces (does not duplicate)
    again = client.post(f"/api/v1/timelines/{timeline['id']}/sequence-from-shots").json()
    re_video = [c for c in again["clips"] if c["track_id"] == video_track]
    assert len(re_video) == 4


def test_track_update_and_delete_cascades_clips(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client)
    timeline = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    video_track = _video_track_id(timeline)
    asset_id = _active_image(client, ctx["shots"][0]["id"])
    clip = client.post(
        f"/api/v1/timelines/{timeline['id']}/clips",
        json={"track_id": video_track, "asset_id": asset_id, "start_time": 0, "end_time": 3},
    ).json()

    muted = client.patch(
        f"/api/v1/timelines/{timeline['id']}/tracks/{video_track}",
        json={"patch": {"muted": 1, "name": "Video-1"}},
    )
    assert muted.status_code == 200
    mt = muted.json()
    assert mt["muted"] == 1 and mt["name"] == "Video-1"

    added = client.post(
        f"/api/v1/timelines/{timeline['id']}/tracks",
        json={"track_type": "SFX", "name": "sfx"},
    )
    assert added.status_code == 201
    assert added.json()["track_type"] == "SFX"

    deleted = client.delete(f"/api/v1/timelines/{timeline['id']}/tracks/{video_track}")
    assert deleted.status_code == 200
    after = client.get(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()
    assert all(c["id"] != clip["id"] for c in after["clips"])  # clips cascaded
    assert not any(t["id"] == video_track for t in after["tracks"])


def test_timeline_patch_and_preview(client: TestClient) -> None:
    ctx = build_episode_with_shot_images(client)
    timeline = client.post(f"/api/v1/episodes/{ctx['episode_id']}/timeline").json()

    updated = client.patch(
        f"/api/v1/timelines/{timeline['id']}",
        json={"patch": {"fps": 30.0, "width": 540, "height": 960, "status": "READY"}},
    )
    assert updated.status_code == 200
    u = updated.json()
    assert u["fps"] == 30.0 and u["width"] == 540 and u["height"] == 960 and u["status"] == "READY"

    # no clips → preview 204
    assert client.get(f"/api/v1/timelines/{timeline['id']}/preview").status_code == 204

    arranged = client.post(f"/api/v1/timelines/{timeline['id']}/sequence-from-shots").json()
    assert len(arranged["clips"]) >= 2
    preview = client.get(f"/api/v1/timelines/{timeline['id']}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
