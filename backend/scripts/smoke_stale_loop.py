"""自主迭代 08 — 过期镜头闭环 live smoke（真实 HTTP，mock providers）。

验证：生成 → storyboard.image_stale=false → 场景环境编辑（P8-T017）→ image_stale=true
（前端「过期」徽标 + 「重新生成过期镜头」入口的数据源）→ 重新生成 → 回落 false。

Usage:
  STUDIO_PORT=17899 ... uv run uvicorn app.main:app --port 17899
  uv run python scripts/smoke_stale_loop.py
"""
import time

import httpx

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=30)


def wait_status(path: str, timeout: float = 30.0) -> dict:
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

    p = c.post("/projects", json={"name": "StaleLoop"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "E1"}).json()
    sc = c.post(f"/episodes/{e['id']}/scenes", json={"name": "天台"}).json()
    sh = c.post(f"/scenes/{sc['id']}/shots", json={"shot_type": "medium", "image_prompt": "manga"}).json()
    print("2. project/episode/scene/shot OK")

    g = c.post(f"/shots/{sh['id']}/generations", json={"type": "image"}).json()
    wait_status(f"/generations/{g['id']}")
    sb = c.get(f"/scenes/{sc['id']}/storyboard").json()
    assert next(s for s in sb["shots"] if s["id"] == sh["id"])["image_stale"] is False
    print("3. storyboard image_stale=false after generation OK")

    scene = c.get(f"/scenes/{sc['id']}").json()
    c.patch(f"/scenes/{sc['id']}", json={"revision": scene["revision"], "patch": {"time_of_day": "夜晚"}})
    sb = c.get(f"/scenes/{sc['id']}/storyboard").json()
    shot = next(s for s in sb["shots"] if s["id"] == sh["id"])
    assert shot["image_stale"] is True, shot
    print("4. scene edit -> storyboard image_stale=true OK (前端「过期」徽标数据源)")

    # 重新生成（对应前端「重新生成过期镜头」入口）
    g2 = c.post(f"/shots/{sh['id']}/generations", json={"type": "image"}).json()
    wait_status(f"/generations/{g2['id']}")
    sb = c.get(f"/scenes/{sc['id']}/storyboard").json()
    assert next(s for s in sb["shots"] if s["id"] == sh["id"])["image_stale"] is False
    print("5. regenerate -> image_stale=false OK")

    print("SMOKE OK: 过期镜头闭环 live 全通（生成->场景编辑stale->重生成清除）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
