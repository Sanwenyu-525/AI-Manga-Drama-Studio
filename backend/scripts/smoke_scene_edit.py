"""自主迭代 06 — 场景信息编辑 live smoke（真实 HTTP，mock providers）。

验证：场景环境 PATCH（时段/光照/天气/氛围/描述）→ revision+1 → P8-T017 连续性重算
（scene_continuity_states 环境基准随之更新）——前端编辑入口触发的正是这条链路。

Usage:
  STUDIO_PORT=17899 ... uv run uvicorn app.main:app --port 17899
  uv run python scripts/smoke_scene_edit.py
"""
import time

import httpx

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=30)


def wait_terminal(path: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = c.get(path).json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            return last
        time.sleep(0.1)
    raise TimeoutError(f"{path} stuck at {last.get('status')}")


def main() -> int:
    health = c.get("/health").json()
    assert health["status"] == "healthy", health
    print("1. health OK")

    p = c.post("/projects", json={"name": "SceneEdit"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "E1"}).json()
    sc = c.post(f"/episodes/{e['id']}/scenes", json={"name": "天台"}).json()
    sh = c.post(f"/scenes/{sc['id']}/shots", json={"shot_type": "medium", "image_prompt": "manga"}).json()
    print("2. project/episode/scene/shot OK")

    # 生成一张图（mock）→ 连续性状态落库
    g = c.post(f"/shots/{sh['id']}/generations", json={"type": "image"}).json()
    done = wait_terminal(f"/generations/{g['id']}")
    assert done["status"] == "completed", done
    c.post(f"/scenes/{sc['id']}/continuity/recompute")
    print("3. generation + continuity recompute OK")

    # 场景环境编辑（前端 ScenePropertiesEditor 的 PATCH 负载）
    scene = c.get(f"/scenes/{sc['id']}").json()
    assert scene["revision"] == 1, scene
    resp = c.patch(
        f"/scenes/{sc['id']}",
        json={"revision": scene["revision"], "patch": {"time_of_day": "夜晚", "lighting": "月光", "mood": "紧张", "description": "雨夜天台的激烈对抗"}},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["time_of_day"] == "夜晚", updated
    assert updated["lighting"] == "月光", updated
    assert updated["revision"] == 2, updated
    print("4. scene environment PATCH OK (revision 1 -> 2):", updated["time_of_day"], updated["lighting"])

    # P8-T017：场景基准变更 → 连续性重算，环境基准已更新（base_state_json 含 夜晚/月光）
    continuity = c.get(f"/scenes/{sc['id']}/continuity").json()
    base = continuity.get("base_state") or {}
    env = base.get("environment") or {}
    assert env.get("time_of_day") == "夜晚", env
    assert env.get("lighting") == "月光", env
    print("5. P8-T017 continuity recompute propagated environment OK:", env)

    print("SMOKE OK: 场景信息编辑链路 live 全通（PATCH -> revision -> 连续性重算）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
