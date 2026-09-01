"""自主迭代 08 — 过期镜头闭环测试（stale 可见 + 批量重生成入口）。

覆盖：生成图后 storyboard.image_stale=false；场景环境编辑（P8-T017）→ 活跃图片资产
stale → storyboard.image_stale=true；重新生成后新资产 active → image_stale=false。
"""

import time


def _wait_status(client, generation_id: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"generation {generation_id} did not finish")


def _make_chain(client) -> dict:
    project = client.post("/api/v1/projects", json={"name": "StaleLoop"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "天台"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga rooftop"},
    ).json()
    return {"project_id": project["id"], "scene_id": scene["id"], "shot_id": shot["id"]}


def test_storyboard_image_stale_false_after_generation(client) -> None:
    chain = _make_chain(client)
    gen = client.post(f"/api/v1/shots/{chain['shot_id']}/generations", json={"type": "image"}).json()
    _wait_status(client, gen["id"])
    storyboard = client.get(f"/api/v1/scenes/{chain['scene_id']}/storyboard").json()
    shot = next(s for s in storyboard["shots"] if s["id"] == chain["shot_id"])
    assert shot["image_stale"] is False  # 新生成资产为 active


def test_scene_edit_marks_shot_image_stale(client) -> None:
    """场景环境编辑（P8-T017）→ 活跃图片资产 stale → storyboard 暴露 image_stale。"""
    chain = _make_chain(client)
    gen = client.post(f"/api/v1/shots/{chain['shot_id']}/generations", json={"type": "image"}).json()
    _wait_status(client, gen["id"])

    scene = client.get(f"/api/v1/scenes/{chain['scene_id']}").json()
    resp = client.patch(
        f"/api/v1/scenes/{chain['scene_id']}",
        json={"revision": scene["revision"], "patch": {"time_of_day": "夜晚"}},
    )
    assert resp.status_code == 200, resp.text

    storyboard = client.get(f"/api/v1/scenes/{chain['scene_id']}/storyboard").json()
    shot = next(s for s in storyboard["shots"] if s["id"] == chain["shot_id"])
    assert shot["image_stale"] is True  # 场景基准变更 → 资产标 stale

    # 活跃资产本身确为 stale（从 Shot ORM 取 active_image_asset_id）
    from app.db.models import Asset, Shot
    from app.db.session import session_factory_provider

    with session_factory_provider()() as session:
        orm_shot = session.get(Shot, chain["shot_id"])
        asset = session.get(Asset, orm_shot.active_image_asset_id) if orm_shot.active_image_asset_id else None
        assert asset is not None and asset.status == "stale"


def test_regenerate_clears_image_stale(client) -> None:
    """重新生成 → 新资产 active → image_stale 回落 false。"""
    chain = _make_chain(client)
    gen = client.post(f"/api/v1/shots/{chain['shot_id']}/generations", json={"type": "image"}).json()
    _wait_status(client, gen["id"])
    scene = client.get(f"/api/v1/scenes/{chain['scene_id']}").json()
    client.patch(
        f"/api/v1/scenes/{chain['scene_id']}",
        json={"revision": scene["revision"], "patch": {"time_of_day": "夜晚"}},
    )
    sb = client.get(f"/api/v1/scenes/{chain['scene_id']}/storyboard").json()
    assert next(s for s in sb["shots"] if s["id"] == chain["shot_id"])["image_stale"] is True

    # 重新生成（recompute 后 asset 未 stale，可再生成；同 shot 幂等门已被旧 generation 终态解除）
    gen2 = client.post(f"/api/v1/shots/{chain['shot_id']}/generations", json={"type": "image"}).json()
    _wait_status(client, gen2["id"])
    sb2 = client.get(f"/api/v1/scenes/{chain['scene_id']}/storyboard").json()
    assert next(s for s in sb2["shots"] if s["id"] == chain["shot_id"])["image_stale"] is False
