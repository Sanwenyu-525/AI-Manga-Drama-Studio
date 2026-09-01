"""自主迭代 07 — AI Director update_scene 工具 live smoke（真实 HTTP，fake LLM）。

验证：导演指令「把这场戏改成夜晚」→ update_scene（R1 自动应用）→ 场景时段更新 +
scene ChangeSet 记录 + P8-T017 连续性重算传播；撤销恢复。

Usage:
  STUDIO_PORT=17899 ... uv run uvicorn app.main:app --port 17899
  uv run python scripts/smoke_agent_scene.py
"""
import time

import httpx

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=30)


def wait_run(path: str, timeout: float = 20.0) -> dict:
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

    p = c.post("/projects", json={"name": "SceneAgent"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "E1"}).json()
    sc = c.post(f"/episodes/{e['id']}/scenes", json={"name": "天台"}).json()
    print("2. project/episode/scene OK")

    # 先设置时段「白天」（让 Agent 修改已设置字段，撤销有明确恢复目标）
    scene = c.get(f"/scenes/{sc['id']}").json()
    c.patch(f"/scenes/{sc['id']}", json={"revision": scene["revision"], "patch": {"time_of_day": "白天"}})
    print("3. scene baseline time_of_day=白天 OK")

    run = c.post(
        "/agent/director/runs",
        json={
            "project_id": p["id"],
            "message": "把这场戏改成夜晚。",
            "selection": {"scene_id": sc["id"], "shot_ids": []},
        },
    ).json()
    done = wait_run(f"/agent/runs/{run['id']}")
    assert done["status"] == "completed", done.get("result")
    updated = c.get(f"/scenes/{sc['id']}").json()
    assert updated["time_of_day"] == "夜晚", updated
    assert updated["revision"] == 3, updated
    print("4. update_scene applied (time_of_day 白天->夜晚, revision 3) OK")

    change_sets = c.get("/agent/change-sets", params={"run_id": run["id"]}).json()
    scene_cs = [cs for cs in change_sets if cs["entity_type"] == "scene" and cs["tool"] == "update_scene"]
    assert len(scene_cs) == 1, change_sets
    assert scene_cs[0]["before"] == {"time_of_day": "白天"}, scene_cs
    assert scene_cs[0]["after"] == {"time_of_day": "夜晚"}, scene_cs
    print("5. scene ChangeSet recorded OK:", scene_cs[0]["before"], "->", scene_cs[0]["after"])

    continuity = c.get(f"/scenes/{sc['id']}/continuity").json()
    env = (continuity.get("base_state") or {}).get("environment") or {}
    assert env.get("time_of_day") == "夜晚", env
    print("6. P8-T017 continuity recompute propagated environment OK:", env)

    resp = c.post(f"/agent/change-sets/{scene_cs[0]['id']}/undo")
    assert resp.status_code == 200, resp.text
    assert c.get(f"/scenes/{sc['id']}").json()["time_of_day"] == "白天"
    print("7. undo restored time_of_day=白天 OK")

    print("SMOKE OK: AI Director update_scene 工具链路 live 全通（应用->ChangeSet->连续性重算->撤销）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
