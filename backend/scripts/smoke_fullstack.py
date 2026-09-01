"""Full-stack integration smoke (live HTTP, mock/fake providers).

Runs the manga production main chain end-to-end against a live backend started
with STUDIO_LLM_MODE=fake / STUDIO_IMAGE_PROVIDER=mock / STUDIO_AUDIO_PROVIDER=mock:

  health → providers → project → episode → analyze(preview+confirm) → shots
  → image generation (mock) → versions → timeline → sequence-from-shots
  → voiceover (mock audio) → render → final-video → download
  + contract checks: asset_type filter, continuity fix route, 202 envelopes.

Usage:
  STUDIO_PORT=17899 STUDIO_DATA_DIR=<tmp> uv run uvicorn app.main:app --port 17899
  uv run python scripts/smoke_fullstack.py
"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=60)
STEP = 0


def ok(label: str) -> None:
    global STEP
    STEP += 1
    print(f"{STEP:2d}. {label}: OK")


def wait_terminal(path: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = c.get(path).json()
        if last.get("status") in ("completed", "failed", "cancelled", "interrupted"):
            return last
        time.sleep(0.2)
    raise TimeoutError(f"{path} stuck at {last.get('status')}")


def wait_operation(op_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = c.get(f"/operations/{op_id}").json()
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(0.2)
    raise TimeoutError(f"operation {op_id} stuck at {last.get('status')}")


def main() -> int:
    # ---- 1. health ----
    health = c.get("/health").json()
    assert health["status"] == "healthy", health
    ok(f"health ({health['backend_version']}, env={health['env']})")

    # ---- 2. providers: statuses must carry the backend enum incl. unavailable ----
    providers = c.get("/providers").json()
    by_id = {p["id"]: p for p in providers}
    assert by_id["mock"]["status"] == "connected", by_id["mock"]
    assert by_id["video_mock"]["status"] == "unavailable", by_id["video_mock"]
    ok(f"providers (image.mock connected, video_mock unavailable, n={len(providers)})")

    # ---- 3. llm/image config reads (fake/mock, masked keys) ----
    llm_cfg = c.get("/llm/config").json()
    assert llm_cfg["mode"] == "fake", llm_cfg
    img_cfg = c.get("/image/config").json()
    assert img_cfg["provider"] == "mock", img_cfg
    assert "api_key" not in img_cfg or not img_cfg.get("api_key"), img_cfg
    ok(f"runtime config (llm={llm_cfg['mode']}, image={img_cfg['provider']})")

    # ---- 4. project + episode ----
    p = c.post("/projects", json={"name": "FullStackSmoke", "aspect_ratio": "9:16"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "第一集"}).json()
    source = (
        "雨夜的便利店门口，少年抱着篮球站在屋檐下。"
        "雨水顺着他的发梢滴落，他盯着手机屏幕上最后一条消息。"
        "店里的灯光把他的影子拉得很长。他咬了咬牙，转身冲进雨里。"
    )
    c.patch(f"/episodes/{e['id']}", json={"revision": e["revision"], "patch": {"source_text": source}})
    ok("project + episode + source_text saved")

    # ---- 5. analyze preview → snapshot confirm (zero second LLM) ----
    preview = c.post(f"/episodes/{e['id']}/analyze/preview").json()
    assert preview["snapshot_id"] and preview["plans"], preview
    started = time.monotonic()
    confirm = c.post(f"/episodes/{e['id']}/analyze", json={"snapshot_id": preview["snapshot_id"]}).json()
    assert "operation_id" in confirm, confirm
    op = wait_operation(confirm["operation_id"])
    assert op["status"] == "completed", op
    scenes = c.get(f"/episodes/{e['id']}/scenes").json()
    assert len(scenes) == len(preview["plans"]), (len(scenes), len(preview["plans"]))
    ok(f"analyze preview+confirm ({len(scenes)} scenes, confirm {time.monotonic() - started:.1f}s)")

    # ---- 6. generate shots (fake LLM) ----
    shots_op = c.post(f"/scenes/{scenes[0]['id']}/generate-shots").json()
    op = wait_operation(shots_op["operation_id"])
    assert op["status"] == "completed", op
    shots = c.get(f"/scenes/{scenes[0]['id']}/shots").json()
    assert shots, shots
    ok(f"generate-shots ({len(shots)} shots)")

    # ---- 7. image generation (mock provider) → asset + version ----
    shot = shots[0]
    gen = c.post(f"/shots/{shot['id']}/generations", json={"type": "image"}).json()
    # double-submit guard: an identical in-flight request must 409 (or 202 if the
    # mock provider already finished — both are legal, duplicated expensive task
    # creation for the same shot+type while active is what's forbidden).
    dup = c.post(f"/shots/{shot['id']}/generations", json={"type": "image"})
    assert dup.status_code in (202, 409), (dup.status_code, dup.text)
    done = wait_terminal(f"/generations/{gen['id']}")
    assert done["status"] == "completed", done.get("error_message")
    asset_id = done["output_asset_id"]
    assert asset_id, done
    versions = c.get(f"/shots/{shot['id']}/versions").json()
    assert any(v["asset_id"] == asset_id and v["media_type"] == "image" for v in versions), versions
    ok(f"image generation → asset {asset_id[:8]} (versions={len(versions)}, dup={dup.status_code})")

    # ---- 8. media access: content + thumbnail ----
    content = c.get(f"/assets/{asset_id}/content")
    assert content.status_code == 200 and len(content.content) > 100, content.status_code
    assert content.headers["content-type"].startswith("image/"), content.headers
    thumb = c.get(f"/assets/{asset_id}/thumbnail")
    assert thumb.status_code == 200, thumb.status_code
    ok(f"media access (content {len(content.content)}B {content.headers['content-type']}, thumbnail {thumb.status_code})")

    # ---- 9. timeline + sequence from shots ----
    tl = c.post(f"/episodes/{e['id']}/timeline").json()
    seq = c.post(f"/timelines/{tl['id']}/sequence-from-shots").json()
    video_clips = [cl for cl in seq["clips"] if cl["track_id"] == next(t["id"] for t in seq["tracks"] if t["track_type"] == "VIDEO")]
    assert video_clips, seq["clips"]
    ok(f"timeline + sequence-from-shots ({len(video_clips)} video clips)")

    # ---- 10. voiceover (mock audio) on a VOICE clip ----
    tl2 = c.get(f"/timelines/{tl['id']}").json()
    voice_track = next(t for t in tl2["tracks"] if t["track_type"] == "VOICE")
    clip = c.post(
        f"/timelines/{tl['id']}/clips",
        json={"track_id": voice_track["id"], "asset_id": asset_id, "start_time": 0, "end_time": 2, "text": "就差最后一种打法了。"},
    ).json()
    vo = c.post(f"/timeline-clips/{clip['id']}/generate-voiceover", json={}).json()
    vo_done = wait_terminal(f"/generations/{vo['id']}")
    assert vo_done["status"] == "completed", vo_done.get("error_message")
    audio = c.get(f"/assets/{vo_done['output_asset_id']}/content")
    assert audio.status_code == 200 and audio.headers["content-type"].startswith("audio/"), audio.headers
    ok(f"voiceover → audio asset {vo_done['output_asset_id'][:8]} ({audio.headers['content-type']})")

    # ---- 11. render → final video → download ----
    render = c.post(f"/timelines/{tl['id']}/render").json()
    r_done = wait_terminal(f"/generations/{render['generation_id']}", timeout=180)
    assert r_done["status"] == "completed", r_done.get("error_message")
    final = c.get(f"/episodes/{e['id']}/final-video").json()
    video = c.get(final["content_url"].replace("/api/v1", ""))
    assert video.status_code == 200 and len(video.content) > 1000, (video.status_code, len(video.content))
    assert video.headers["content-type"].startswith("video/"), video.headers
    ok(f"render → FINAL_VIDEO ({final['version_number']}, {len(video.content) // 1024}KB {video.headers['content-type']})")

    # ---- 12. asset list: asset_type filter contract ----
    images = c.get(f"/projects/{p['id']}/assets", params={"asset_type": "image"}).json()
    assert images["total"] >= 1 and all(it["type"] == "image" for it in images["items"]), images
    item = images["items"][0]
    assert item.get("name") and item.get("source_type"), item  # browser grouping fields
    legacy = c.get(f"/projects/{p['id']}/assets", params={"type": "image"}).json()
    assert legacy["total"] > images["total"] or all(it["type"] == "image" for it in legacy["items"]), legacy
    ok(f"asset list filter (asset_type=image → {images['total']}, legacy ?type= → {legacy['total']} (unfiltered, as documented))")

    # ---- 13. contract: continuity fix route exists, legacy 'runs' route does not ----
    # Route-level 404s surface the unified envelope with code=NOT_FOUND, while an
    # existing route with a missing entity answers code=ENTITY_NOT_FOUND.
    missing = c.post("/agent/continuity/runs", json={"scene_id": scenes[0]["id"]})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND", missing.text
    fix = c.post("/agent/continuity/fix", json={"warning_id": "nonexistent", "patch": {}})
    assert fix.status_code == 404 and fix.json()["error"]["code"] == "ENTITY_NOT_FOUND", fix.text
    ok("continuity routes (/agent/continuity/runs 404 route-missing; /agent/continuity/fix exists)")

    # ---- 14. generations recent + queue status ----
    recent = c.get("/generations/recent").json()
    assert any(g["id"] == r_done["id"] for g in recent), "render generation not in recent"
    queue = c.get("/generations/queue-status").json()
    ok(f"generations recent ({len(recent)}) + queue-status (pending={queue.get('pending')})")

    print(f"\nFULLSTACK SMOKE: all {STEP} steps passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\nFULLSTACK SMOKE FAILED: {exc}")
        print(json.dumps(getattr(exc, "args", [""]), ensure_ascii=False, default=str)[:2000])
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"\nFULLSTACK SMOKE FAILED (transport): {exc}")
        sys.exit(1)
