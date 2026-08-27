"""TASK-012 tests — voiceover generation flow: API 202 → worker → AUDIO asset
registered under vg:clip:{id}:AUDIO (immutable versions) + VOICE clip re-bound."""
import asyncio
import time

from fastapi.testclient import TestClient

from app.db.models import Asset
from app.generations.worker import run_generation
from app.services.audio_service import clip_audio_version_group


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _wait_done(client: TestClient, generation_id: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"voiceover generation {generation_id} did not finish in {timeout}s")


def _setup_timeline_with_shot_image(client: TestClient) -> tuple[dict, str]:
    """project → episode → timeline + one shot with a generated image asset.
    Returns ({...ids}, image_asset_id)."""
    project = client.post("/api/v1/projects", json={"name": "VOProject"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "duration": 2.0, "image_prompt": "p"},
    ).json()
    gen = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(gen["id"])
    done = _wait_done(client, gen["id"])
    assert done["status"] == "completed", done.get("error_message")
    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()
    return {
        "project_id": project["id"],
        "episode_id": episode["id"],
        "scene_id": scene["id"],
        "timeline_id": timeline["id"],
        "shot_id": shot["id"],
    }, done["output_asset_id"]


def _add_clip(client: TestClient, ctx: dict, track_type: str, asset_id: str) -> tuple[str, str]:
    """Create a clip on the first track of the given type; returns (clip_id, track_id)."""
    tl = client.get(f"/api/v1/timelines/{ctx['timeline_id']}").json()
    track = next(t for t in tl["tracks"] if t["track_type"] == track_type)
    clip = client.post(
        f"/api/v1/timelines/{ctx['timeline_id']}/clips",
        json={
            "track_id": track["id"],
            "asset_id": asset_id,
            "start_time": 0,
            "end_time": 2,
        },
    )
    assert clip.status_code == 201, clip.text
    body = clip.json()
    return body["id"], track["id"]


def test_voiceover_end_to_end_binds_audio_version(client: TestClient, session_factory) -> None:
    ctx, image_asset_id = _setup_timeline_with_shot_image(client)
    clip_id, _track_id = _add_clip(client, ctx, "VOICE", image_asset_id)

    # give the clip its narration copy via the clip PATCH contract
    patched = client.patch(f"/api/v1/timeline-clips/{clip_id}", json={"patch": {"text": "你好，漫剧。"}})
    assert patched.status_code == 200
    assert patched.json()["text"] == "你好，漫剧。"

    resp = client.post(f"/api/v1/timeline-clips/{clip_id}/generate-voiceover", json={})
    assert resp.status_code == 202, resp.text
    gen = resp.json()
    assert gen["type"] == "audio"
    assert gen["status"] == "queued"

    done = _wait_done(client, gen["id"])
    assert done["status"] == "completed", done.get("error_message")
    audio_asset_id = done["output_asset_id"]
    assert audio_asset_id

    # the VOICE clip is re-bound to the synthesized audio
    tl = client.get(f"/api/v1/timelines/{ctx['timeline_id']}").json()
    vo_clip = next(c for c in tl["clips"] if c["id"] == clip_id)
    assert vo_clip["asset"]["type"] == "audio"
    assert vo_clip["asset"]["id"] == audio_asset_id

    # the file served through the asset pipeline is a genuine WAV
    content = client.get(f"/api/v1/assets/{audio_asset_id}/content")
    assert content.status_code == 200
    assert content.content[:4] == b"RIFF"

    # immutable version group numbering
    factory = session_factory[0]
    with factory() as s:
        asset = s.get(Asset, audio_asset_id)
        assert asset.version_group_id == clip_audio_version_group(clip_id)
        assert asset.version_number == 1

    # second synthesis on the same clip → V2 exists beside V1, clip advances to it
    second = client.post(
        f"/api/v1/timeline-clips/{clip_id}/generate-voiceover",
        json={"text": "第二版台词", "rate": "+10%"},
    )
    assert second.status_code == 202
    done2 = _wait_done(client, second.json()["id"])
    assert done2["status"] == "completed", done2.get("error_message")
    v2_id = done2["output_asset_id"]
    assert v2_id != audio_asset_id

    with factory() as s:
        a1 = s.get(Asset, audio_asset_id)
        a2 = s.get(Asset, v2_id)
        assert a1.version_number == 1 and a2.version_number == 2
        assert a2.version_group_id == a1.version_group_id


def test_voiceover_validation_errors(client: TestClient) -> None:
    ctx, image_asset_id = _setup_timeline_with_shot_image(client)

    # non-VOICE track → 422
    video_clip_id, _ = _add_clip(client, ctx, "VIDEO", image_asset_id)
    r = client.post(f"/api/v1/timeline-clips/{video_clip_id}/generate-voiceover", json={"text": "x"})
    assert r.status_code == 422

    # no text anywhere → 422
    vo_clip_id, _ = _add_clip(client, ctx, "VOICE", image_asset_id)
    r = client.post(f"/api/v1/timeline-clips/{vo_clip_id}/generate-voiceover", json={"text": "   "})
    assert r.status_code == 422

    # unknown provider → 422 (fail fast before queuing)
    r = client.post(
        f"/api/v1/timeline-clips/{vo_clip_id}/generate-voiceover",
        json={"text": "词", "provider": "bogus"},
    )
    assert r.status_code == 422

    # malformed rate → 422
    r = client.post(
        f"/api/v1/timeline-clips/{vo_clip_id}/generate-voiceover",
        json={"text": "词", "rate": "+bad"},
    )
    assert r.status_code == 422

    # missing clip → 404
    r = client.post("/api/v1/timeline-clips/does-not-exist/generate-voiceover", json={"text": "词"})
    assert r.status_code == 404


def test_service_raises_typed_not_found(client: TestClient) -> None:
    """Direct service call surfaces the studio-domain 404 (contract parity)."""
    from app.core.errors import NotFoundError

    from app.services.audio_service import AudioService

    factory = None
    # reuse whatever isolated factory the client fixture installed
    from app.db import session as db_session_module

    factory = db_session_module.session_factory_provider()
    with factory() as s:
        service = AudioService(s)
        try:
            from app.domain.generation import VoiceoverGenerateRequest

            service.create_voiceover_generation("nope", VoiceoverGenerateRequest(text="x"))
            raised = False
        except NotFoundError:
            raised = True
        assert raised
