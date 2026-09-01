"""自主迭代 05 — AI Director 刷新恢复 live smoke（真实 HTTP，fake LLM）。

验证：跑一次 director 会话（R1 update_shot 自动执行 → completed）→
GET /agent/runs/{id} 返回 messages 转录 → GET /agent/runs?project_id=&limit=1
返回最近会话（新在前）——前端刷新后据此水合对话流。

Usage:
  STUDIO_PORT=17899 ... uv run uvicorn app.main:app --port 17899
  uv run python scripts/smoke_agent_refresh.py
"""
import time

import httpx

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=30)


def wait_terminal(path: str, timeout: float = 20.0) -> dict:
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

    p = c.post("/projects", json={"name": "AgentRefresh"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "E1"}).json()
    sc = c.post(f"/episodes/{e['id']}/scenes", json={"name": "S1"}).json()
    sh = c.post(f"/scenes/{sc['id']}/shots", json={"shot_type": "medium", "image_prompt": "manga"}).json()
    print("2. project/episode/scene/shot OK")

    run = c.post(
        "/agent/director/runs",
        json={
            "project_id": p["id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [sh["id"]], "scene_id": sc["id"]},
        },
    ).json()
    done = wait_terminal(f"/agent/runs/{run['id']}")
    assert done["status"] == "completed", done
    print("3. director run completed OK")

    messages = done["messages"]
    assert len(messages) >= 2, messages
    assert messages[0]["role"] == "user" and messages[0]["content"] == "把这个镜头改成近景。", messages
    assert messages[-1]["role"] == "assistant" and messages[-1]["content"], messages
    print("4. run detail messages transcript OK:", [m["content"] for m in messages])

    runs = c.get("/agent/runs", params={"project_id": p["id"], "limit": 3}).json()
    assert len(runs) >= 1 and runs[0]["id"] == run["id"], runs
    assert all("messages" in r for r in runs), runs
    print("5. list runs newest-first with messages OK:", runs[0]["id"])

    print("SMOKE OK: AI Director 刷新恢复链路 live 全通")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
