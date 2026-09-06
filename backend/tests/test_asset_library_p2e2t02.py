"""P2-E2-T02 项目作用域 Asset Library（docs/roadmap/phase-2-core-product.md）.

覆盖（按 commit 增量追加）：
- cursor 分页：往返无重复/漏项、非法 cursor 422、cursor+offset 互斥 422、offset 向后兼容
- 筛选：source / shot_id / scene_id / created_from~to、跨项目 422、不存在 404、非法值 422
"""

import asyncio
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.generations.worker import run_generation


def _png(seed: int = 0) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), ((seed * 37) % 256, 80, 40)).save(buf, "PNG")
    return buf.getvalue()


def _project(client: TestClient, name: str = "P2E2T02Lib") -> dict:
    return client.post("/api/v1/projects", json={"name": name}).json()


def _upload(client: TestClient, project_id: str, seed: int = 0, filename: str = "img.png") -> dict:
    resp = client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": (filename, _png(seed), "image/png")},
        data={"asset_type": "image"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _shot(client: TestClient, project_id: str, scene_name: str = "S1") -> tuple[dict, dict]:
    episode = client.post(f"/api/v1/projects/{project_id}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": scene_name}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga, street"},
    ).json()
    return scene, shot


# --- cursor 分页 ------------------------------------------------------------

def test_cursor_pagination_roundtrip_no_dup_no_loss(client: TestClient) -> None:
    project = _project(client)
    for i in range(5):
        _upload(client, project["id"], seed=i, filename=f"f{i}.png")

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get(f"/api/v1/projects/{project['id']}/assets", params=params).json()
        assert body["total"] == 5
        seen.extend(it["id"] for it in body["items"])
        pages += 1
        cursor = body.get("next_cursor")
        if not cursor:
            break
        assert pages < 10  # 防死循环

    assert pages == 3  # 2+2+1
    assert len(set(seen)) == 5  # 无重复、无漏项


def test_cursor_last_page_next_cursor_none(client: TestClient) -> None:
    project = _project(client)
    _upload(client, project["id"], seed=1)
    body = client.get(f"/api/v1/projects/{project['id']}/assets", params={"limit": 50}).json()
    assert body["total"] == 1
    assert body.get("next_cursor") is None


def test_cursor_invalid_422(client: TestClient) -> None:
    project = _project(client)
    _upload(client, project["id"])
    resp = client.get(f"/api/v1/projects/{project['id']}/assets", params={"cursor": "not-a-cursor!!"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cursor_offset_mutually_exclusive_422(client: TestClient) -> None:
    project = _project(client)
    _upload(client, project["id"], seed=1)
    _upload(client, project["id"], seed=2)
    first = client.get(f"/api/v1/projects/{project['id']}/assets", params={"limit": 1}).json()
    assert first["next_cursor"]
    resp = client.get(
        f"/api/v1/projects/{project['id']}/assets",
        params={"cursor": first["next_cursor"], "offset": 1},
    )
    assert resp.status_code == 422


def test_offset_still_works_backward_compatible(client: TestClient) -> None:
    project = _project(client)
    for i in range(3):
        _upload(client, project["id"], seed=i, filename=f"c{i}.png")
    page = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"limit": 1, "offset": 1}
    ).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1
    # offset 语义不变：与 limit=50 全量相比取到第 2 行
    full = client.get(f"/api/v1/projects/{project['id']}/assets", params={"limit": 50}).json()
    assert page["items"][0]["id"] == full["items"][1]["id"]


# --- 筛选 -------------------------------------------------------------------

def test_filter_source(client: TestClient) -> None:
    project = _project(client)
    _upload(client, project["id"])
    imported = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"source": "imported"}
    ).json()
    assert imported["total"] == 1
    generated = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"source": "generated"}
    ).json()
    assert generated["total"] == 0


def test_filter_source_invalid_422(client: TestClient) -> None:
    project = _project(client)
    resp = client.get(f"/api/v1/projects/{project['id']}/assets", params={"source": "bogus"})
    assert resp.status_code == 422


def test_filter_shot_id_generated_asset(client: TestClient) -> None:
    project = _project(client)
    _, shot = _shot(client, project["id"])
    g = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    asyncio.run(run_generation(g["id"]))
    done = client.get(f"/api/v1/generations/{g['id']}").json()
    assert done["status"] == "completed"

    body = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"shot_id": shot["id"]}
    ).json()
    assert body["total"] >= 1
    assert {it["id"] for it in body["items"]} >= {done["output_asset_id"]}


def test_filter_shot_id_404_unknown(client: TestClient) -> None:
    project = _project(client)
    resp = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"shot_id": "does-not-exist"}
    )
    assert resp.status_code == 404


def test_filter_shot_id_cross_project_422(client: TestClient) -> None:
    p_a = _project(client, "ProjA")
    p_b = _project(client, "ProjB")
    _, shot_b = _shot(client, p_b["id"])
    resp = client.get(
        f"/api/v1/projects/{p_a['id']}/assets", params={"shot_id": shot_b["id"]}
    )
    assert resp.status_code == 422


def test_filter_scene_id(client: TestClient) -> None:
    project = _project(client)
    scene1, shot1 = _shot(client, project["id"], scene_name="S1")
    _shot(client, project["id"], scene_name="S2")
    g = client.post(f"/api/v1/shots/{shot1['id']}/generations", json={"type": "image"}).json()
    asyncio.run(run_generation(g["id"]))
    done = client.get(f"/api/v1/generations/{g['id']}").json()
    assert done["status"] == "completed"

    body = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"scene_id": scene1["id"]}
    ).json()
    assert done["output_asset_id"] in {it["id"] for it in body["items"]}


def test_filter_scene_id_404_unknown(client: TestClient) -> None:
    project = _project(client)
    resp = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"scene_id": "does-not-exist"}
    )
    assert resp.status_code == 404


def test_filter_shot_and_scene_mutually_exclusive_422(client: TestClient) -> None:
    project = _project(client)
    scene, shot = _shot(client, project["id"])
    resp = client.get(
        f"/api/v1/projects/{project['id']}/assets",
        params={"shot_id": shot["id"], "scene_id": scene["id"]},
    )
    assert resp.status_code == 422


def test_filter_created_range(client: TestClient) -> None:
    project = _project(client)
    asset = _upload(client, project["id"])
    created = asset["created_at"]

    inside = client.get(
        f"/api/v1/projects/{project['id']}/assets",
        params={"created_from": "2020-01-01", "created_to": "2030-01-01"},
    ).json()
    assert asset["id"] in {it["id"] for it in inside["items"]}

    # 精确到秒的窄窗口仍命中同一资产（同一 created_at 上下各 1 秒）
    narrow = client.get(
        f"/api/v1/projects/{project['id']}/assets",
        params={"created_from": created, "created_to": created},
    ).json()
    assert asset["id"] in {it["id"] for it in narrow["items"]}

    outside = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"created_from": "2030-01-02"}
    ).json()
    assert outside["total"] == 0


def test_filter_created_invalid_422(client: TestClient) -> None:
    project = _project(client)
    resp = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"created_from": "not-a-date"}
    )
    assert resp.status_code == 422


# --- 导入校验 ---------------------------------------------------------------

def _import(
    client: TestClient,
    project_id: str,
    content: bytes,
    filename: str = "img.png",
    asset_type: str = "image",
    extra: dict | None = None,
):
    fields: dict = {"asset_type": asset_type}
    if extra:
        fields.update(extra)
    return client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": (filename, content, "application/octet-stream")},
        data=fields,
    )


def test_import_rejects_spoofed_mime(client: TestClient) -> None:
    project = _project(client)
    # 文本内容套 png 扩展名 → 文件头校验拒绝
    resp = _import(client, project["id"], b"this is not an image at all" * 10, filename="fake.png")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_import_rejects_image_declared_as_video(client: TestClient) -> None:
    project = _project(client)
    resp = _import(client, project["id"], _png(), filename="photo.mp4", asset_type="video")
    # 有 ffprobe 时为"不可识别视频"422；无 ffprobe 时图片头伪装同样 422
    assert resp.status_code == 422


def test_import_rejects_empty_file(client: TestClient) -> None:
    project = _project(client)
    resp = _import(client, project["id"], b"", filename="empty.png")
    assert resp.status_code == 422


def test_import_rejects_path_traversal_source_name(client: TestClient) -> None:
    project = _project(client)
    resp = _import(
        client, project["id"], _png(), extra={"source_name": "../../evil.png"}
    )
    assert resp.status_code == 422


def test_import_with_shot_link_and_filter(client: TestClient) -> None:
    project = _project(client)
    _, shot = _shot(client, project["id"])
    resp = _import(client, project["id"], _png(), extra={"shot_id": shot["id"]})
    assert resp.status_code == 201
    asset_id = resp.json()["id"]

    body = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"shot_id": shot["id"]}
    ).json()
    assert asset_id in {it["id"] for it in body["items"]}


def test_import_with_unknown_shot_404(client: TestClient) -> None:
    project = _project(client)
    resp = _import(client, project["id"], _png(), extra={"shot_id": "does-not-exist"})
    assert resp.status_code == 404


def test_import_with_cross_project_shot_422(client: TestClient) -> None:
    p_a = _project(client, "ProjA")
    p_b = _project(client, "ProjB")
    _, shot_b = _shot(client, p_b["id"])
    resp = _import(client, p_a["id"], _png(), extra={"shot_id": shot_b["id"]})
    assert resp.status_code == 422


# --- 详情追溯 ---------------------------------------------------------------

def test_detail_integrity_ok_for_imported(client: TestClient) -> None:
    project = _project(client)
    asset = _upload(client, project["id"])
    detail = client.get(f"/api/v1/assets/{asset['id']}").json()
    integrity = detail["integrity"]
    assert integrity["file_exists"] is True
    assert integrity["checksum_match"] is True
    assert integrity["checked_at"]
    assert detail["version_context"] == {
        "version_number": None,
        "is_active": False,
        "is_master": False,
    }
    assert detail["shot_context"] is None


def test_detail_integrity_missing_file(client: TestClient) -> None:
    from app.services.asset_service import project_dir

    project = _project(client)
    asset = _upload(client, project["id"])
    (project_dir(project["id"]) / asset["file_path"]).unlink()

    detail = client.get(f"/api/v1/assets/{asset['id']}").json()
    assert detail["integrity"]["file_exists"] is False
    assert detail["integrity"]["checksum_match"] is None


def test_detail_traces_generation_and_shot(client: TestClient) -> None:
    project = _project(client)
    scene, shot = _shot(client, project["id"])
    g = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    asyncio.run(run_generation(g["id"]))
    done = client.get(f"/api/v1/generations/{g['id']}").json()
    assert done["status"] == "completed"

    detail = client.get(f"/api/v1/assets/{done['output_asset_id']}").json()
    assert detail["generation_id"] == g["id"]
    assert detail["shot_id"] == shot["id"]
    assert detail["shot_context"]["shot_id"] == shot["id"]
    assert detail["shot_context"]["scene_id"] == scene["id"]
    assert detail["integrity"]["checksum_match"] is True
    # 新生成即该镜头的 active 版本
    assert detail["version_context"]["is_active"] is True
    # Generation 展开走 provenance 端点
    prov = client.get(f"/api/v1/assets/{done['output_asset_id']}/provenance").json()
    assert prov["generation"]["id"] == g["id"]


def test_detail_shot_context_from_import_link(client: TestClient) -> None:
    project = _project(client)
    scene, shot = _shot(client, project["id"])
    resp = _import(client, project["id"], _png(), extra={"shot_id": shot["id"]})
    detail = client.get(f"/api/v1/assets/{resp.json()['id']}").json()
    assert detail["shot_context"]["shot_id"] == shot["id"]
    assert detail["shot_context"]["scene_id"] == scene["id"]


# --- 归档 / 恢复 / 物理删除 + 引用守卫 ----------------------------------------

def test_archive_restore_roundtrip(client: TestClient) -> None:
    project = _project(client)
    asset = _upload(client, project["id"])

    archived = client.post(f"/api/v1/assets/{asset['id']}/archive").json()
    assert archived["id"] == asset["id"]

    # 归档后：列表默认不可见，详情 404，include_deleted 可见
    assert client.get(f"/api/v1/assets/{asset['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/assets").json()["total"] == 0
    assert client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"include_deleted": "true"}
    ).json()["total"] == 1

    # 归档幂等
    assert client.post(f"/api/v1/assets/{asset['id']}/archive").status_code == 200

    restored = client.post(f"/api/v1/assets/{asset['id']}/restore").json()
    assert restored["id"] == asset["id"]
    assert client.get(f"/api/v1/assets/{asset['id']}").status_code == 200
    # 恢复幂等
    assert client.post(f"/api/v1/assets/{asset['id']}/restore").status_code == 200


def test_archive_unknown_404(client: TestClient) -> None:
    assert client.post("/api/v1/assets/does-not-exist/archive").status_code == 404
    assert client.post("/api/v1/assets/does-not-exist/restore").status_code == 404


def test_archive_blocked_by_shot_active_reference(client: TestClient) -> None:
    project = _project(client)
    _, shot = _shot(client, project["id"])
    g = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    asyncio.run(run_generation(g["id"]))
    done = client.get(f"/api/v1/generations/{g['id']}").json()
    assert done["status"] == "completed"

    # 新生成即 active → 归档被拒，引用清单含 shot_active
    resp = client.post(f"/api/v1/assets/{done['output_asset_id']}/archive")
    assert resp.status_code == 409
    body = resp.json()["error"]
    assert body["code"] == "CONFLICT"
    kinds = {r["kind"] for r in body["details"]["references"]}
    assert "shot_active" in kinds


def test_physical_delete_requires_confirm_and_archive(client: TestClient) -> None:
    project = _project(client)
    asset = _upload(client, project["id"])

    # 未归档 + 无 confirm → 422（两步确认缺一不可）
    assert client.delete(f"/api/v1/assets/{asset['id']}").status_code == 422
    assert client.delete(f"/api/v1/assets/{asset['id']}", params={"confirm": "true"}).status_code == 422

    client.post(f"/api/v1/assets/{asset['id']}/archive")
    assert client.delete(f"/api/v1/assets/{asset['id']}").status_code == 422

    result = client.delete(
        f"/api/v1/assets/{asset['id']}", params={"confirm": "true"}
    ).json()
    assert result["deleted"] is True
    assert result["asset_id"] == asset["id"]
    assert any(p.endswith(".png") for p in result["files_removed"])

    # 文件落盘删除 + 记录删除（恢复也 404）
    from app.services.asset_service import project_dir

    assert not (project_dir(project["id"]) / asset["file_path"]).exists()
    assert client.post(f"/api/v1/assets/{asset['id']}/restore").status_code == 404
    assert client.get(f"/api/v1/assets/{asset['id']}").status_code == 404


def test_physical_delete_blocked_by_timeline_clip(client: TestClient) -> None:
    from app.db import session as db_session_module
    from app.db.models import TimelineClip

    project = _project(client)
    asset = _upload(client, project["id"])
    asset_id = asset["id"]
    client.post(f"/api/v1/assets/{asset_id}/archive")

    # 归档后绑一个 timeline clip（绕过 API 的 live 校验，直写行模拟回填/历史状态）
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    timeline = client.post(f"/api/v1/episodes/{episode['id']}/timeline").json()
    track_id = timeline["tracks"][0]["id"]
    with db_session_module.session_factory_provider()() as s:
        s.add(
            TimelineClip(
                timeline_id=timeline["id"],
                track_id=track_id,
                asset_id=asset_id,
                start_time=0,
                end_time=1,
            )
        )
        s.commit()

    resp = client.delete(f"/api/v1/assets/{asset_id}", params={"confirm": "true"})
    assert resp.status_code == 409
    kinds = {r["kind"] for r in resp.json()["error"]["details"]["references"]}
    assert "timeline_clip" in kinds
    # 记录与文件完好（保护性拒绝不产生副作用）
    assert client.get(f"/api/v1/assets/{asset_id}").status_code == 404  # 仍归档态
    from app.services.asset_service import project_dir

    assert (project_dir(project["id"]) / asset["file_path"]).exists()
