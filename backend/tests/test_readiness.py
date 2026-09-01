"""自主迭代 04 — 生产就绪度（GET /projects/{id}/readiness）测试。

覆盖：空项目全零 / 角色 MASTER 覆盖 / 场景地点绑定覆盖（未绑定·绑定无 MASTER·绑定有 MASTER）/
开放连续性警告计数 / 项目 404。
"""

import io

from PIL import Image


def _make_project(client) -> dict:
    return client.post("/api/v1/projects", json={"name": "就绪度"}).json()


def _make_episode_scene(client, project_id: str, scene_name: str = "S1") -> dict:
    episode = client.post(f"/api/v1/projects/{project_id}/episodes", json={"title": "E1"}).json()
    return client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": scene_name}).json()


def _import_image(client, project_id: str, color: tuple = (5, 5, 5)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "PNG")
    resp = client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": ("ref.png", buf.getvalue(), "image/png")},
        data={"asset_type": "image"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _location_with_master(client, project_id: str, name: str = "天台") -> dict:
    loc = client.post(f"/api/v1/projects/{project_id}/locations", json={"name": name}).json()
    asset = _import_image(client, project_id, color=(12, 34, 56))
    version = client.post(f"/api/v1/locations/{loc['id']}/versions", json={"asset_id": asset}).json()
    client.post(f"/api/v1/locations/{loc['id']}/versions/{version['id']}/activate")
    return loc


def _bind_scene(client, scene_id: str, location_id: str) -> None:
    scene = client.get(f"/api/v1/scenes/{scene_id}").json()
    resp = client.patch(
        f"/api/v1/scenes/{scene_id}",
        json={"revision": scene["revision"], "patch": {"location_id": location_id}},
    )
    assert resp.status_code == 200, resp.text


def test_readiness_empty_project_is_all_zero(client) -> None:
    project = _make_project(client)
    data = client.get(f"/api/v1/projects/{project['id']}/readiness").json()
    assert data["characters"] == {"total": 0, "ready": 0, "missing": 0}
    assert data["scene_binding"] == {
        "scenes_total": 0,
        "bound": 0,
        "bound_with_master": 0,
        "unbound": 0,
    }
    assert data["continuity_open"] == 0


def test_readiness_character_master_coverage(client) -> None:
    project = _make_project(client)
    # 角色 A：无 MASTER；角色 B：有 MASTER（版本 + 激活）
    client.post(f"/api/v1/projects/{project['id']}/characters", json={"name": "无版本"})
    char_b = client.post(f"/api/v1/projects/{project['id']}/characters", json={"name": "有版本"}).json()
    asset = _import_image(client, project["id"], color=(1, 1, 1))
    version = client.post(f"/api/v1/characters/{char_b['id']}/versions", json={"asset_id": asset}).json()
    client.post(f"/api/v1/characters/{char_b['id']}/versions/{version['id']}/activate")

    data = client.get(f"/api/v1/projects/{project['id']}/readiness").json()
    assert data["characters"] == {"total": 2, "ready": 1, "missing": 1}


def test_readiness_scene_binding_coverage(client) -> None:
    project = _make_project(client)
    # 地点 1 有 MASTER；地点 2 无 MASTER
    loc_master = _location_with_master(client, project["id"], "天台")
    loc_no_master = client.post(f"/api/v1/projects/{project['id']}/locations", json={"name": "更衣室"}).json()

    scene_bound_ready = _make_episode_scene(client, project["id"], "S1")
    _bind_scene(client, scene_bound_ready["id"], loc_master["id"])
    scene_bound_no_master = _make_episode_scene(client, project["id"], "S2")
    _bind_scene(client, scene_bound_no_master["id"], loc_no_master["id"])
    _make_episode_scene(client, project["id"], "S3")

    data = client.get(f"/api/v1/projects/{project['id']}/readiness").json()
    assert data["scene_binding"] == {
        "scenes_total": 3,
        "bound": 2,
        "bound_with_master": 1,
        "unbound": 1,
    }


def test_readiness_counts_open_continuity_warnings(client, session_factory) -> None:
    project = _make_project(client)
    scene = _make_episode_scene(client, project["id"], "S1")
    factory, _ = session_factory
    from app.db.models import ContinuityWarning

    with factory() as session:
        session.add(
            ContinuityWarning(
                project_id=project["id"],
                scene_id=scene["id"],
                category="costume",
                severity="warning",
                message="服装变化",
                status="open",
            )
        )
        session.commit()

    data = client.get(f"/api/v1/projects/{project['id']}/readiness").json()
    assert data["continuity_open"] == 1


def test_readiness_project_not_found_404(client) -> None:
    resp = client.get("/api/v1/projects/proj_nope/readiness")
    assert resp.status_code == 404
