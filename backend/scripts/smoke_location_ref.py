"""自主迭代 03 — 场景地点参考图注入 live smoke（真实 HTTP，mock providers）。

验证：Location 创建 → 版本 → MASTER → 场景绑定 → 参考图预览（地点）→
生成溯源（LOCATION_REFERENCE 行）→ 生成明细 references（location_name）。

Usage:
  STUDIO_PORT=17899 ... uv run uvicorn app.main:app --port 17899
  uv run python scripts/smoke_location_ref.py
"""
import io
import time

import httpx
from PIL import Image

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=30)


def wait_terminal(path: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = c.get(path).json()
        if last.get("status") in ("completed", "failed", "cancelled", "interrupted"):
            return last
        time.sleep(0.2)
    raise TimeoutError(f"{path} stuck at {last.get('status')}")


def main() -> int:
    health = c.get("/health").json()
    assert health["status"] == "healthy", health
    print("1. health OK")

    p = c.post("/projects", json={"name": "LocSmoke"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "E1"}).json()
    sc = c.post(f"/episodes/{e['id']}/scenes", json={"name": "天台"}).json()
    print("2. project/episode/scene OK")

    loc = c.post(f"/projects/{p['id']}/locations", json={"name": "天台"}).json()
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "PNG")
    ast = c.post(
        f"/projects/{p['id']}/assets/import",
        files={"file": ("loc.png", buf.getvalue(), "image/png")},
        data={"asset_type": "image"},
    ).json()
    ver = c.post(f"/locations/{loc['id']}/versions", json={"asset_id": ast["id"]}).json()
    c.post(f"/locations/{loc['id']}/versions/{ver['id']}/activate")
    print("3. location + version + activate MASTER OK")

    sc2 = c.patch(f"/scenes/{sc['id']}", json={"revision": sc["revision"], "patch": {"location_id": loc["id"]}}).json()
    assert sc2["location_id"] == loc["id"], sc2
    print("4. scene bound to location OK")

    sh = c.post(f"/scenes/{sc['id']}/shots", json={"shot_type": "medium", "image_prompt": "rooftop basketball court, manga"}).json()
    refs = c.get(f"/shots/{sh['id']}/reference-images").json()
    assert len(refs) == 1 and refs[0]["location_id"] == loc["id"], refs
    assert refs[0]["location_name"] == "天台", refs
    print("5. preview references -> location MASTER OK:", refs)

    g = c.post(f"/shots/{sh['id']}/generations", json={"type": "image"}).json()
    inputs = c.get(f"/generations/{g['id']}/inputs").json()
    lr = [i for i in inputs["inputs"] if i["reference_type"] == "LOCATION_REFERENCE"]
    assert len(lr) == 1 and lr[0]["role"] == "location_reference", lr
    print("6. generation_inputs has LOCATION_REFERENCE row OK")

    done = wait_terminal(f"/generations/{g['id']}")
    assert done["status"] == "completed", done
    detail = c.get(f"/generations/{g['id']}").json()
    refs2 = detail["references"]
    assert len(refs2) == 1 and refs2[0]["location_name"] == "天台", refs2
    assert refs2[0]["source"] == "auto" and refs2[0]["location_id"] == loc["id"], refs2
    print("7. generation detail references -> location provenance OK:", refs2)

    # 自主迭代 04：生产就绪度（角色/场景绑定/连续性聚合，与上述状态一致）
    r = c.get(f"/projects/{p['id']}/readiness").json()
    assert r["scene_binding"]["scenes_total"] == 1, r
    assert r["scene_binding"]["bound_with_master"] == 1, r
    assert r["scene_binding"]["unbound"] == 0, r
    assert r["characters"]["total"] == 0 and r["characters"]["missing"] == 0, r
    assert r["continuity_open"] == 0, r
    print("8. readiness aggregation OK:", r)

    print("SMOKE OK: 场景地点参考图注入链路 + 生产就绪度 live 全通")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
