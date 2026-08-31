"""P4-E3-T02 (AC-2) tests — Timeline transition + revision + undo.

Covers the acceptance gap "调整时长/基础转场有 revision 与 undo":
- transition field (cut/fade/dissolve) on clips, validated, carried into render.
- optimistic concurrency: PATCH with a stale revision → 409 (never silent overwrite).
- user Timeline edits recorded as ChangeSets (source="timeline") and undone
  through the shared POST /agent/change-sets/{id}/undo machinery.
"""

import json

from fastapi.testclient import TestClient

from app.generations.worker import run_generation

DEFAULT_TRANSITION = "cut"


def _drive(generation_id: str) -> None:
    import asyncio

    asyncio.run(run_generation(generation_id))


def _build(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P4-E3-T02"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "duration": 3.0, "image_prompt": "manga a"},
    ).json()
    gen = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(gen["id"])
    deadline = 0
    import time

    while True:
        done = client.get(f"/api/v1/generations/{gen['id']}").json()
        if done["status"] in ("completed", "failed"):
            break
        if deadline > 200:
            raise TimeoutError("image generation timeout")
        time.sleep(0.05)
        deadline += 1
    assert done["status"] == "completed"
    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()
    video_track = next(t["id"] for t in timeline["tracks"] if t["track_type"] == "VIDEO")
    versions = client.get(f"/api/v1/shots/{shot['id']}/image-versions").json()
    asset_id = next(v["asset_id"] for v in versions if v["is_active"])
    return {"episode_id": episode["id"], "timeline_id": timeline["id"], "video_track": video_track, "asset_id": asset_id}


def _add_clip(client: TestClient, ctx: dict, **overrides) -> dict:
    body = {
        "track_id": ctx["video_track"],
        "asset_id": ctx["asset_id"],
        "start_time": 0,
        "end_time": 3,
        **overrides,
    }
    resp = client.post(f"/api/v1/timelines/{ctx['timeline_id']}/clips", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_clip_transition_default_and_validation(client: TestClient) -> None:
    ctx = _build(client)
    clip = _add_clip(client, ctx)
    assert clip["transition"] == DEFAULT_TRANSITION
    assert clip["revision"] == 1

    # set a fade transition
    faded = client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"transition": "fade", "revision": clip["revision"]}},
    ).json()
    assert faded["transition"] == "fade"
    assert faded["revision"] == 2

    # invalid transition → 422
    bad = client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"transition": "warp", "revision": faded["revision"]}},
    )
    assert bad.status_code == 422


def test_clip_revision_guard_conflict_409(client: TestClient) -> None:
    ctx = _build(client)
    clip = _add_clip(client, ctx)

    # stale revision → 409 (second writer loses instead of silently overwriting)
    stale = client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"start_time": 1.0, "end_time": 4.0, "revision": clip["revision"]}},
    )
    assert stale.status_code == 200
    current = stale.json()

    conflict = client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"start_time": 2.0, "end_time": 5.0, "revision": clip["revision"]}},
    )
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error"]["details"]["current_revision"] == current["revision"]

    # with the fresh revision the same edit succeeds
    ok = client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"start_time": 2.0, "end_time": 5.0, "revision": current["revision"]}},
    )
    assert ok.status_code == 200
    assert ok.json()["start_time"] == 2.0 and ok.json()["end_time"] == 5.0


def test_timeline_edit_recorded_as_change_set_and_undo(client: TestClient) -> None:
    ctx = _build(client)
    clip = _add_clip(client, ctx)

    # edit: duration + transition → one recorded timeline ChangeSet
    updated = client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"end_time": 5.0, "transition": "dissolve", "revision": clip["revision"]}},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    change_sets = client.get("/api/v1/agent/change-sets?entity_id=" + clip["id"]).json()
    timeline_cs = [cs for cs in change_sets if cs["source"] == "timeline" and not cs["undone"]]
    assert len(timeline_cs) == 1
    cs = timeline_cs[0]
    assert cs["entity_type"] == "timeline_clip"
    assert cs["tool"] == "timeline.edit"
    assert cs["before"]["end_time"] == 3.0 and cs["before"]["transition"] == "cut"
    assert cs["after"]["end_time"] == 5.0 and cs["after"]["transition"] == "dissolve"

    # undo through the shared machinery → clip restored, revision bumped again
    undone = client.post(f"/api/v1/agent/change-sets/{cs['id']}/undo")
    assert undone.status_code == 200
    restored = client.get(f"/api/v1/timelines/{ctx['timeline_id']}").json()
    restored_clip = next(c for c in restored["clips"] if c["id"] == clip["id"])
    assert restored_clip["end_time"] == 3.0
    assert restored_clip["transition"] == "cut"
    assert restored_clip["revision"] == 3

    # undo is terminal: a second undo → 409
    again = client.post(f"/api/v1/agent/change-sets/{cs['id']}/undo")
    assert again.status_code == 409


def test_render_plan_carries_transition(client: TestClient, session_factory) -> None:
    ctx = _build(client)
    clip = _add_clip(client, ctx, end_time=4)
    client.patch(
        f"/api/v1/timeline-clips/{clip['id']}",
        json={"patch": {"transition": "fade", "revision": clip["revision"]}},
    )
    gen = client.post(f"/api/v1/timelines/{ctx['timeline_id']}/render").json()
    assert gen["status"] == "queued"
    # GenerationRead does not expose parameters — read the queued row directly.
    factory, _ = session_factory
    with factory() as session:
        from app.db.models import Generation

        row = session.get(Generation, gen["generation_id"])
        params = json.loads(row.parameters)
    video_clips = [c for c in params["clips"] if c["kind"] in ("image", "video")]
    assert video_clips
    assert all(c["transition"] in ("cut", "fade", "dissolve") for c in video_clips)
    assert any(c["transition"] == "fade" for c in video_clips)


def test_ffmpeg_graph_xfade_segments_and_duration() -> None:
    """Pure graph-builder test: cross-fades become xfade chains, cuts split
    segments (concat), and effective_duration accounts for the overlap."""
    from app.providers.render.base import RenderClip, RenderRequest
    from app.providers.render.ffmpeg import build_filter_complex, effective_duration

    req = RenderRequest(
        output_path="out.mp4",
        width=720,
        height=1280,
        fps=24,
        clips=[
            RenderClip(source_path="a.png", kind="image", start=0, end=3),
            RenderClip(source_path="b.png", kind="image", start=3, end=6, transition="fade"),
            RenderClip(source_path="c.png", kind="image", start=6, end=9),  # back to hard cut
            RenderClip(source_path="d.png", kind="image", start=9, end=12, transition="dissolve"),
        ],
    )
    parts, maps = build_filter_complex(req, srt_path=None)
    joined = ";".join(parts)
    assert "xfade=transition=fade" in joined
    assert "xfade=transition=dissolve" in joined
    assert joined.count("xfade=") == 2
    # segments: [a→b] + [c→d] → concat of 2 segment streams
    assert "concat=n=2" in joined
    assert maps[0] == "-map [vout]"

    # hard cuts everywhere → plain single concat, no xfade
    plain = RenderRequest(
        output_path="out.mp4",
        width=720,
        height=1280,
        fps=24,
        clips=[
            RenderClip(source_path="a.png", kind="image", start=0, end=3),
            RenderClip(source_path="b.png", kind="image", start=3, end=6),
        ],
    )
    parts2, _ = build_filter_complex(plain, srt_path=None)
    assert "xfade=" not in ";".join(parts2)
    assert "concat=n=2" in ";".join(parts2)

    # effective duration subtracts cross-fade overlaps only
    assert effective_duration(req.clips) == 12.0 - 0.5 - 0.5
    assert effective_duration(plain.clips) == 6.0
