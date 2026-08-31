"""P2-E1-T01 — Analysis Snapshot: preview 落库不可变快照，confirm 只提交快照。

验收（phase-2-core-product P2-E1-T01）：
- Confirm 写入内容与用户看到的 snapshot 字段逐项一致（零二次 LLM 调用）。
- 源文本 / episode revision 改变后旧 snapshot 过期（409 + operation failed）。
- 重复 Confirm 幂等：不重复创建 Scene。
- 刷新后能读取 preview 状态（GET /analysis-snapshots/latest）。
- 模型 / prompt / schema version 与 source hash 可追溯（provenance 字段）。

FakeLLM 是确定性的，本套件的重点是「写入的=预览的」由机制保证而非模型复现。
"""

import time

from fastapi.testclient import TestClient

from tests.test_script_planning import NOVEL_TEXT, _wait_operation, create_episode_with_source


def _preview(client: TestClient, episode_id: str) -> dict:
    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze/preview")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _confirm(client: TestClient, episode_id: str, snapshot_id: str) -> dict:
    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze", json={"snapshot_id": snapshot_id})
    assert resp.status_code == 202, resp.text
    return _wait_operation(client, resp.json()["operation_id"])


def test_confirm_writes_exactly_the_previewed_plans(client: TestClient) -> None:
    """AC1: 写入内容与 snapshot 逐项一致（title/location/time/description/mood）。"""
    _, episode_id = create_episode_with_source(client)
    preview = _preview(client, episode_id)

    done = _confirm(client, episode_id, preview["snapshot_id"])
    assert done["status"] == "completed", done.get("error")
    assert done["result"]["scene_plans"] == preview["plans"]

    scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
    assert len(scenes) == len(preview["plans"])
    for plan, scene in zip(preview["plans"], scenes, strict=True):
        assert scene["name"] == plan["title"]
        assert scene["location_id"] == plan["location"]
        assert scene["time_of_day"] == plan["time"]
        assert scene["description"] == plan["description"]
        assert scene["mood"] == plan["mood"]


def test_confirm_is_idempotent_no_duplicate_scenes(client: TestClient) -> None:
    """AC3: 重复 Confirm 幂等，不重复创建 Scene。"""
    _, episode_id = create_episode_with_source(client)
    snapshot_id = _preview(client, episode_id)["snapshot_id"]

    first = _confirm(client, episode_id, snapshot_id)
    assert first["status"] == "completed"
    first_ids = first["result"]["created_scene_ids"]

    second = _confirm(client, episode_id, snapshot_id)
    assert second["status"] == "completed", second.get("error")
    assert second["result"]["created_scene_ids"] == first_ids

    scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
    assert len(scenes) == len(first_ids)  # 没有翻倍


def test_snapshot_expires_when_source_text_changed(client: TestClient) -> None:
    """AC2a: 预览后改原文 → confirm 409 语义（operation failed）+ snapshot expired。"""
    project_id, episode_id = create_episode_with_source(client)
    snapshot_id = _preview(client, episode_id)["snapshot_id"]

    episode = client.get(f"/api/v1/episodes/{episode_id}").json()
    patched = client.patch(
        f"/api/v1/episodes/{episode_id}",
        json={"revision": episode["revision"], "patch": {"source_text": NOVEL_TEXT + "\n新增段落。"}},
    )
    assert patched.status_code == 200, patched.text

    done = _confirm(client, episode_id, snapshot_id)
    assert done["status"] == "failed"
    assert "preview" in (done.get("error") or "").lower()

    latest = client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json()
    assert latest["status"] == "expired"
    # 过期后原文未再预览前不可 confirm
    again = _confirm(client, episode_id, snapshot_id)
    assert again["status"] == "failed"


def test_snapshot_expires_when_revision_changed_without_source_change(client: TestClient) -> None:
    """AC2b: 仅改标题（source 未变）也过期——LLM 输入含标题，且 AC 明示 revision 变更即失效。"""
    _, episode_id = create_episode_with_source(client)
    snapshot_id = _preview(client, episode_id)["snapshot_id"]

    episode = client.get(f"/api/v1/episodes/{episode_id}").json()
    patched = client.patch(
        f"/api/v1/episodes/{episode_id}",
        json={"revision": episode["revision"], "patch": {"title": "改名后的第一集"}},
    )
    assert patched.status_code == 200

    done = _confirm(client, episode_id, snapshot_id)
    assert done["status"] == "failed"


def test_latest_snapshot_rehydrates_after_refresh(client: TestClient) -> None:
    """AC4: 刷新后可读取 preview 状态（pending → confirmed 全程可追溯）。"""
    _, episode_id = create_episode_with_source(client)
    preview = _preview(client, episode_id)

    latest = client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json()
    assert latest["id"] == preview["snapshot_id"]
    assert latest["status"] == "pending"
    assert latest["plans"] == preview["plans"]
    assert latest["episode_revision"] >= 1

    _confirm(client, episode_id, preview["snapshot_id"])
    latest = client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json()
    assert latest["status"] == "confirmed"
    assert latest["created_scene_ids"]


def test_snapshot_provenance_is_traceable(client: TestClient) -> None:
    """AC5: source_hash / prompt_version / schema_version / model 可追溯。"""
    _, episode_id = create_episode_with_source(client)
    preview = _preview(client, episode_id)

    latest = client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json()
    assert latest["source_hash"] == preview["source_hash"]
    assert latest["prompt_version"]
    assert latest["schema_version"]


def test_confirm_unknown_snapshot_fails(client: TestClient) -> None:
    _, episode_id = create_episode_with_source(client)
    done = _confirm(client, episode_id, "no-such-snapshot")
    assert done["status"] == "failed"


def test_confirm_snapshot_from_other_episode_fails(client: TestClient) -> None:
    """跨剧集提交 snapshot → 422 语义（operation failed），不写入。"""
    _, episode_a = create_episode_with_source(client)
    _, episode_b = create_episode_with_source(client)
    snapshot_b = _preview(client, episode_b)["snapshot_id"]

    done = _confirm(client, episode_a, snapshot_b)
    assert done["status"] == "failed"
    scenes = client.get(f"/api/v1/episodes/{episode_a}/scenes").json()
    assert scenes == []


def test_latest_snapshot_none_when_never_previewed(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "无快照"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "空", "source_text": "正文"}
    ).json()
    resp = client.get(f"/api/v1/episodes/{episode['id']}/analysis-snapshots/latest")
    assert resp.status_code == 200
    assert resp.json() is None


def test_legacy_analyze_without_snapshot_still_works(client: TestClient) -> None:
    """向后兼容：不带 snapshot_id 的 analyze 走原 LLM 路径。"""
    _, episode_id = create_episode_with_source(client)
    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    assert resp.status_code == 202
    done = _wait_operation(client, resp.json()["operation_id"])
    assert done["status"] == "completed", done.get("error")
    assert len(done["result"]["created_scene_ids"]) >= 2
    # 留一点缓冲避免与下一次 client fixture 竞争
    time.sleep(0.05)
