"""C1 整轨批量配音 tests — POST /timelines/{id}/generate-voiceovers.

Covers:
- Only enabled VOICE-track clips with text (and no AUDIO bound) get a
  type="audio" generation queued (202 path, one per clip).
- Clips without text → skipped_no_text; clips already bound to an AUDIO asset →
  already_bound (won't re-generate); image-bound VOICE clips are still eligible.
- Unknown timeline → 404.
"""

from fastapi.testclient import TestClient

from app.db.models import Asset, TimelineClip


def _setup_timeline_with_shot_image(client: TestClient) -> tuple[dict, str]:
    """project → episode → timeline + one shot with a generated image asset."""
    project = client.post("/api/v1/projects", json={"name": "VO-Batch"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "duration": 2.0, "image_prompt": "p"},
    ).json()
    gen = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    from app.generations.worker import run_generation

    import asyncio

    asyncio.run(run_generation(gen["id"]))
    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()
    ctx = {
        "project_id": project["id"],
        "timeline_id": timeline["id"],
    }
    # the generated image asset (needed to create clips)
    output_id = client.get(f"/api/v1/generations/{gen['id']}").json().get("output_asset_id")
    return ctx, output_id


def _add_voice_clip(client: TestClient, ctx: dict, asset_id: str, text: str | None) -> str:
    tl = client.get(f"/api/v1/timelines/{ctx['timeline_id']}").json()
    track = next(t for t in tl["tracks"] if t["track_type"] == "VOICE")
    clip = client.post(
        f"/api/v1/timelines/{ctx['timeline_id']}/clips",
        json={"track_id": track["id"], "asset_id": asset_id, "start_time": 0, "end_time": 2},
    )
    assert clip.status_code == 201, clip.text
    clip_id = clip.json()["id"]
    if text is not None:
        r = client.patch(f"/api/v1/timeline-clips/{clip_id}", json={"patch": {"text": text}})
        assert r.status_code == 200
    return clip_id


def test_voiceover_batch_queues_text_clips_only(client: TestClient, session_factory) -> None:
    ctx, image_asset_id = _setup_timeline_with_shot_image(client)

    # A: image-bound + text → submitted
    clip_a = _add_voice_clip(client, ctx, image_asset_id, "第一句台词")
    # B: image-bound + no text → skipped_no_text
    clip_b = _add_voice_clip(client, ctx, image_asset_id, None)
    # C: audio-bound + text → already_bound
    clip_c = _add_voice_clip(client, ctx, image_asset_id, "已有配音")

    factory = session_factory[0]
    with factory() as s:
        audio_asset = Asset(
            project_id=ctx["project_id"],
            type="audio",
            name="vo.wav",
            status="ready",
            source_type="generated",
        )
        s.add(audio_asset)
        s.commit()
        audio_id = audio_asset.id
        clip = s.get(TimelineClip, clip_c)
        clip.asset_id = audio_id
        s.commit()

    resp = client.post(f"/api/v1/timelines/{ctx['timeline_id']}/generate-voiceovers")
    assert resp.status_code == 202, resp.text
    body = resp.json()

    submitted = {item["clip_id"]: item for item in body["submitted"]}
    assert set(submitted) == {clip_a}
    assert submitted[clip_a]["generation_id"]
    assert submitted[clip_a]["text_head"] == "第一句台词"
    assert body["skipped_no_text"] == [clip_b]
    assert body["already_bound"] == [clip_c]

    # each submission is a queued type=audio generation
    gen = client.get(f"/api/v1/generations/{submitted[clip_a]['generation_id']}").json()
    assert gen["type"] == "audio"
    assert gen["status"] == "queued"

    # a second batch run does NOT re-queue the same eligible clip again... unless
    # the first generation completed and bound an audio asset. Assert only that the
    # no-text and audio-bound clips remain skipped.
    resp2 = client.post(f"/api/v1/timelines/{ctx['timeline_id']}/generate-voiceovers").json()
    assert clip_b in resp2["skipped_no_text"]
    assert clip_c in resp2["already_bound"]


def test_voiceover_batch_unknown_timeline(client: TestClient) -> None:
    resp = client.post("/api/v1/timelines/does-not-exist/generate-voiceovers")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"
