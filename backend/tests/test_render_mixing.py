"""TASK-013 tests — render mixing: the plan now carries VOICE/MUSIC/SFX + SUBTITLE
clips; the mock renderer emits a real PCM stream and burned captions; the ffmpeg
graph builder is asserted purely (no binary needed)."""
import asyncio
import struct
import time

from fastapi.testclient import TestClient

from app.generations.worker import run_generation
from app.providers.registry import resolve_render_provider_id
from app.providers.render.base import RenderClip, RenderRequest


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _wait_done(client: TestClient, generation_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"generation {generation_id} did not finish in {timeout}s")


def _build_scene(client: TestClient, with_dialogue: bool) -> dict:
    """Project → episode → 1 scene × 1 shot (with image + optional dialogue)
    → timeline → sequence-from-shots (adds VIDEO clip, SUBTITLE clip if dialogue)."""
    project = client.post("/api/v1/projects", json={"name": "MixProject"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot_payload = {"shot_type": "medium", "duration": 2.0, "image_prompt": "p"}
    if with_dialogue:
        shot_payload["dialogue"] = "这是烧录字幕的台词"
    shot = client.post(f"/api/v1/scenes/{scene['id']}/shots", json=shot_payload).json()
    gen = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(gen["id"])
    done = _wait_done(client, gen["id"])
    assert done["status"] == "completed", done.get("error_message")
    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()
    arranged = client.post(f"/api/v1/timelines/{timeline['id']}/sequence-from-shots").json()
    assert len(arranged["clips"]) == 1 + (1 if with_dialogue else 0)
    return {
        "project_id": project["id"],
        "episode_id": episode["id"],
        "timeline_id": timeline["id"],
        "shot_id": shot["id"],
        "image_asset_id": done["output_asset_id"],
    }


def _add_voice_clip_and_generate(client: TestClient, ctx: dict, text: str) -> str:
    """VOICE clip (bound to a placeholder asset first) → voiceover generation → asset id."""
    tl = client.get(f"/api/v1/timelines/{ctx['timeline_id']}").json()
    voice_track = next(t for t in tl["tracks"] if t["track_type"] == "VOICE")
    clip = client.post(
        f"/api/v1/timelines/{ctx['timeline_id']}/clips",
        json={
            "track_id": voice_track["id"],
            "asset_id": ctx["image_asset_id"],  # placeholder binding; replaced by synthesis
            "start_time": 0,
            "end_time": 2,
            "text": text,
        },
    ).json()
    resp = client.post(f"/api/v1/timeline-clips/{clip['id']}/generate-voiceover", json={})
    assert resp.status_code == 202, resp.text
    done = _wait_done(client, resp.json()["id"])
    assert done["status"] == "completed", done.get("error_message")
    return done["output_asset_id"]


def _render(client: TestClient, ctx: dict) -> dict:
    resp = client.post(f"/api/v1/timelines/{ctx['timeline_id']}/render")
    assert resp.status_code == 202, resp.text
    done = _wait_done(client, resp.json()["generation_id"])
    return done


def _final_video_asset(session_factory, asset_id: str):
    factory = session_factory[0]
    with factory() as s:
        from app.db.models import Asset

        return s.get(Asset, asset_id)


def _asset_meta(asset) -> dict:
    """AssetService stores meta_json as str(dict) — parse with a JSON-first fallback."""
    import ast
    import json

    raw = asset.meta_json or "{}"
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return ast.literal_eval(raw)


def _avi_chunks(data: bytes) -> dict[str, list[bytes]]:
    """Minimal top-level RIFF reader: every 'movi' subchunk tag → payloads."""
    chunks: dict[str, list[bytes]] = {}
    pos = 12  # skip RIFF header
    while pos + 8 <= len(data):
        tag = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body = data[pos + 8 : pos + 8 + size]
        if tag == b"LIST":
            list_type = body[:4]
            if list_type == b"movi":
                inner = 4
                while inner + 8 <= len(body):
                    itag = body[inner : inner + 4]
                    isize = struct.unpack("<I", body[inner + 4 : inner + 8])[0]
                    chunks.setdefault(itag.decode("latin1"), []).append(
                        body[inner + 8 : inner + 8 + isize]
                    )
                    inner += 8 + isize + (isize % 2)
        pos += 8 + size + (size % 2)
    return chunks


# ------------------------------------------------------------------ pure units


def test_ffmpeg_graph_builder_units() -> None:
    from app.providers.render.ffmpeg import build_filter_complex, build_srt, escape_subtitles_path

    req = RenderRequest(
        output_path="out.mp4",
        width=720,
        height=1280,
        fps=24,
        clips=[RenderClip(source_path="a.png", kind="image", start=0, end=2)],
        audio_clips=[
            RenderClip(source_path="v1.wav", kind="audio", start=0.5, end=2),
            RenderClip(source_path="m.mp3", kind="audio", start=3, end=5),
        ],
        subtitle_clips=[RenderClip(source_path="", kind="subtitle", start=0, end=1.5, text="字幕A")],
    )
    parts, maps = build_filter_complex(req, srt_path=None)

    joined = ";".join(parts)
    assert "amix=inputs=2" in joined
    assert "adelay=500:all=1" in joined
    assert "adelay=3000:all=1" in joined
    assert maps[0] == "-map [vout]"
    assert "-map [amix]" in maps

    # with subtitles the video chain routes through the subtitles filter
    parts2, maps2 = build_filter_complex(req, srt_path=None)  # no srt → direct chain
    assert "[vfin]" not in ";".join(parts2)

    class _FakeSrtPath:
        def as_posix(self) -> str:
            return r"C:/tmp/out.srt"

    assert escape_subtitles_path(_FakeSrtPath()) == "subtitles='C\\:/tmp/out.srt'"

    srt = build_srt(
        [
            RenderClip(source_path="", kind="subtitle", start=1, end=2.5, text="第二句"),
            RenderClip(source_path="", kind="subtitle", start=0, end=1, text="第一句"),
            RenderClip(source_path="", kind="subtitle", start=2, end=3, text="   "),  # dropped
        ]
    )
    lines = srt.strip().splitlines()
    assert lines[0] == "1"
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "第一句" in srt and "第二句" in srt and "第一句" not in lines[1]


# ------------------------------------------------------------------ e2e (mock renderer)


def test_render_without_audio_stays_silent(client: TestClient, session_factory) -> None:
    ctx = _build_scene(client, with_dialogue=False)
    done = _render(client, ctx)
    assert done["status"] == "completed", done.get("error_message")
    asset = _final_video_asset(session_factory, done["output_asset_id"])
    extra = _asset_meta(asset).get("render") or {}
    assert not extra.get("has_audio", False)


def test_render_mixes_voiceover_and_burns_subtitles(client: TestClient, session_factory) -> None:
    ctx = _build_scene(client, with_dialogue=True)
    vo_asset_id = _add_voice_clip_and_generate(client, ctx, "旁白：比赛开始的哨声响了。")

    # check subtitle clip exists on the timeline (from sequence-from-shots)
    tl = client.get(f"/api/v1/timelines/{ctx['timeline_id']}").json()
    subs = [c for c in tl["clips"] if c["text"]]
    assert any(c["text"].startswith("这是烧录字幕") for c in subs)

    done = _render(client, ctx)
    assert done["status"] == "completed", done.get("error_message")
    payload = done  # generation read
    assert payload["output_asset_id"]

    import json  # noqa: F401 — kept for parity with other suites

    asset = _final_video_asset(session_factory, payload["output_asset_id"])
    extra = _asset_meta(asset).get("render") or {}
    assert extra.get("has_audio") is True
    assert extra.get("subtitle_clips", 0) >= 1
    # final export must not be confused with the voiceover intermediate
    assert asset.id != vo_asset_id

    provider = resolve_render_provider_id()
    if provider == "mock":
        # locate the physical file through AssetService (project-relative path)
        from app.services.asset_service import project_dir

        path = project_dir(ctx["project_id"]) / asset.file_path
        raw = path.read_bytes()
        chunks = _avi_chunks(raw)
        wb = chunks.get("01wb", [])
        assert wb, "expected an PCM audio chunk ('01wb') in the mock AVI"
        samples = struct.unpack(f"<{len(wb[0]) // 2}h", wb[0])
        assert any(abs(s) > 100 for s in samples), "PCM bed should contain the tone (non-silent)"
