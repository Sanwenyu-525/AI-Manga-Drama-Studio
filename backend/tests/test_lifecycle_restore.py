"""P2-E2-T01 — 归档/恢复/删除语义：restore × 5 + trash + 冲突守卫。

验收（phase-2-core-product P2-E2-T01）：
- 五实体可恢复；恢复已存在行 = 幂等 no-op；未知 id → 404。
- 父删子不可见：shot 恢复要求场景 live（409 + recovery 指引）。
- 恢复冲突 409 且不覆盖：编号被 live 行占用时拒绝并给出冲突行。
- 级联恢复按时间戳划界：同 cascade 的行复活，独立删除的行保持删除。
- trash 列出四类删除行（时间倒序）供审阅与逐行恢复。
- episode 部分唯一索引：删除后重建同号不 500（P1-E1-T02 遗漏的补齐）。
"""

from fastapi.testclient import TestClient


def _tree(client: TestClient, shots: int = 2) -> dict:
    project = client.post("/api/v1/projects", json={"name": "生命周期"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "EP1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "SC1"}
    ).json()
    made = [
        client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "medium"}).json()
        for _ in range(shots)
    ]
    character = client.post(
        f"/api/v1/projects/{project['id']}/characters", json={"name": "阿珍"}
    ).json()
    return {
        "project_id": project["id"], "episode_id": episode["id"],
        "scene_id": scene["id"], "shots": made, "character_id": character["id"],
    }


def _live_shot_ids(client: TestClient, scene_id: str) -> set[str]:
    return {s["id"] for s in client.get(f"/api/v1/scenes/{scene_id}/shots").json()}


def test_shot_restore_roundtrip_and_idempotent(client: TestClient) -> None:
    ctx = _tree(client)
    victim = ctx["shots"][0]["id"]
    assert client.delete(f"/api/v1/shots/{victim}").status_code == 200
    assert victim not in _live_shot_ids(client, ctx["scene_id"])

    restored = client.post(f"/api/v1/shots/{victim}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == victim
    assert victim in _live_shot_ids(client, ctx["scene_id"])

    # 已 live 再恢复 = 幂等 no-op；未知 id = 404。
    assert client.post(f"/api/v1/shots/{victim}/restore").status_code == 200
    assert client.post("/api/v1/shots/no-such-shot/restore").status_code == 404


def test_shot_restore_refuses_deleted_parent(client: TestClient) -> None:
    ctx = _tree(client)
    victim = ctx["shots"][0]["id"]
    client.delete(f"/api/v1/shots/{victim}")
    client.delete(f"/api/v1/scenes/{ctx['scene_id']}")

    resp = client.post(f"/api/v1/shots/{victim}/restore")
    assert resp.status_code == 409
    body = resp.json()["error"]
    assert body["details"]["recovery"] == "restore_scene"

    # 先恢复场景，镜头仍是删除态（场景删除不级联），再恢复镜头成功。
    assert client.post(f"/api/v1/scenes/{ctx['scene_id']}/restore").status_code == 200
    assert victim not in _live_shot_ids(client, ctx["scene_id"])
    assert client.post(f"/api/v1/shots/{victim}/restore").status_code == 200


def test_shot_restore_number_conflict_does_not_overwrite(client: TestClient) -> None:
    ctx = _tree(client)
    by_number = {s["shot_number"]: s for s in client.get(f"/api/v1/scenes/{ctx['scene_id']}/shots").json()}
    victim = by_number[2]
    assert client.delete(f"/api/v1/shots/{victim['id']}").status_code == 200
    # 新建镜头占用 2 号（max(live)+1）。
    newcomer = client.post(f"/api/v1/scenes/{ctx['scene_id']}/shots", json={"shot_type": "wide"}).json()
    assert newcomer["shot_number"] == 2

    resp = client.post(f"/api/v1/shots/{victim['id']}/restore")
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["conflict"] == "number"
    assert details["live_shot_id"] == newcomer["id"]
    # 新行不受影响。
    assert client.get(f"/api/v1/shots/{newcomer['id']}").json()["shot_type"] == "wide"


def test_scene_restore_roundtrip_and_parent_guard(client: TestClient) -> None:
    ctx = _tree(client)
    assert client.delete(f"/api/v1/scenes/{ctx['scene_id']}").status_code == 200
    assert client.get(f"/api/v1/scenes/{ctx['scene_id']}").status_code == 404
    # 镜头被父删隐藏（P1-E1-T02 存量语义）。
    assert client.get(f"/api/v1/shots/{ctx['shots'][0]['id']}").status_code == 404

    restored = client.post(f"/api/v1/scenes/{ctx['scene_id']}/restore")
    assert restored.status_code == 200, restored.text
    assert client.get(f"/api/v1/shots/{ctx['shots'][0]['id']}").status_code == 200

    # 父剧集删除后恢复场景 → 409。
    client.delete(f"/api/v1/episodes/{ctx['episode_id']}")
    resp = client.post(f"/api/v1/scenes/{ctx['scene_id']}/restore")
    assert resp.status_code in (404, 409)  # 场景随级联已删：先恢复剧集
    assert client.post(f"/api/v1/episodes/{ctx['episode_id']}/restore").status_code == 200
    assert client.get(f"/api/v1/scenes/{ctx['scene_id']}").status_code == 200


def test_episode_restore_cascade_scope_and_number_reuse(client: TestClient) -> None:
    ctx = _tree(client)
    # 独立删除一个镜头（时间戳与后续级联不同）→ 恢复剧集时保持删除。
    lone = ctx["shots"][0]["id"]
    assert client.delete(f"/api/v1/shots/{lone}").status_code == 200

    assert client.delete(f"/api/v1/episodes/{ctx['episode_id']}").status_code == 200
    assert client.get(f"/api/v1/episodes/{ctx['episode_id']}").status_code == 404

    restored = client.post(f"/api/v1/episodes/{ctx['episode_id']}/restore")
    assert restored.status_code == 200, restored.text
    assert ctx["scene_id"] in {s["id"] for s in client.get(f"/api/v1/episodes/{ctx['episode_id']}/scenes").json()}
    assert ctx["shots"][1]["id"] in _live_shot_ids(client, ctx["scene_id"])
    assert lone not in _live_shot_ids(client, ctx["scene_id"])


def test_episode_delete_then_recreate_same_number(client: TestClient) -> None:
    """部分唯一索引回归：删除 EP1 后重建不再 500（与场景/镜头一致）。"""
    project = client.post("/api/v1/projects", json={"name": "编号"}).json()
    first = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "A"}).json()
    assert first["episode_number"] == 1
    assert client.delete(f"/api/v1/episodes/{first['id']}").status_code == 200
    second = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "B"})
    assert second.status_code == 201, second.text
    assert second.json()["episode_number"] == 1
    # 此时恢复旧 EP1 → 编号冲突 409（不覆盖新行）。
    resp = client.post(f"/api/v1/episodes/{first['id']}/restore")
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["conflict"] == "number"


def test_character_restore_revives_links(client: TestClient) -> None:
    ctx = _tree(client)
    shot_id = ctx["shots"][0]["id"]
    revision = client.get(f"/api/v1/shots/{shot_id}").json()["revision"]
    patched = client.patch(
        f"/api/v1/shots/{shot_id}",
        json={"revision": revision, "patch": {"character_ids": [ctx["character_id"]]}},
    )
    assert patched.status_code == 200, patched.text

    assert client.delete(f"/api/v1/characters/{ctx['character_id']}").status_code == 200
    assert client.get(f"/api/v1/characters/{ctx['character_id']}").status_code == 404

    restored = client.post(f"/api/v1/characters/{ctx['character_id']}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["shot_count"] == 1  # 链接保留，恢复即复活


def test_project_restore_cascade_and_trash(client: TestClient) -> None:
    ctx = _tree(client)
    # 项目级附属：地点 + 文档随级联消失，直接访问 404（AC: 父删子不可见）。
    location = client.post(
        f"/api/v1/projects/{ctx['project_id']}/locations", json={"name": "天台"}
    ).json()
    document = client.post(
        f"/api/v1/projects/{ctx['project_id']}/documents",
        json={"title": "设定", "doc_type": "worldview", "content": "x"},
    ).json()

    assert client.delete(f"/api/v1/projects/{ctx['project_id']}").status_code == 200
    assert client.get(f"/api/v1/projects/{ctx['project_id']}").status_code == 404
    assert client.get(f"/api/v1/locations/{location['id']}").status_code == 404
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 404

    trash = client.get(f"/api/v1/projects/{ctx['project_id']}/trash").json()
    kinds = {(item["entity_type"], item["id"]) for item in trash}
    assert ("episode", ctx["episode_id"]) in kinds
    assert ("scene", ctx["scene_id"]) in kinds
    assert ("shot", ctx["shots"][0]["id"]) in kinds
    assert ("character", ctx["character_id"]) in kinds
    deleted_ats = [item["deleted_at"] for item in trash]
    assert deleted_ats == sorted(deleted_ats, reverse=True)

    restored = client.post(f"/api/v1/projects/{ctx['project_id']}/restore")
    assert restored.status_code == 200, restored.text
    assert client.get(f"/api/v1/episodes/{ctx['episode_id']}").status_code == 200
    assert client.get(f"/api/v1/locations/{location['id']}").status_code == 200
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 200
    assert client.get(f"/api/v1/projects/{ctx['project_id']}/trash").json() == []


def test_trash_unknown_project_404(client: TestClient) -> None:
    assert client.get("/api/v1/projects/no-such-project/trash").status_code == 404
    assert client.post("/api/v1/projects/no-such-project/restore").status_code == 404
