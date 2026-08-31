"""设定文档库 tests (database-v0.1 §32.6, api-event-contract §20.1, mvp-spec DOC-*).

Covers the DOC-002/003/004 acceptance path:
- CRUD with revision optimistic concurrency + soft delete
- doc_type validation (422) and entity-link validation (404/422, same-project)
- source_hash recomputation on content change
- Agent injection: the analysis key (snapshot source_hash) depends on the project's
  setting documents, so a changed document forces re-analysis (DOC-004).
"""

from fastapi.testclient import TestClient

NOVEL_TEXT = (
    "夜色降临，城市的天台上沈亦握着篮球。顾言走上来说：'最后一种打法，要么赢，要么散。'"
    "第二天体育馆决赛，哨声响起，沈亦带球突破，起跳投篮，球进，全场欢呼。"
)


def create_project(client: TestClient, name: str = "设定文档验收") -> dict:
    return client.post("/api/v1/projects", json={"name": name, "aspect_ratio": "9:16"}).json()


def create_episode_with_source(client: TestClient) -> tuple[str, str]:
    project = create_project(client)
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes",
        json={"title": "第一集", "source_text": NOVEL_TEXT},
    ).json()
    return project["id"], episode["id"]


def create_document(client: TestClient, project_id: str, **overrides) -> dict:
    body = {"doc_type": "character_setting", "title": "人物设定·沈亦", "content": "沈亦：黑色短发，外冷内热。"}
    body.update(overrides)
    resp = client.post(f"/api/v1/projects/{project_id}/documents", json=body)
    assert resp.status_code == 201
    return resp.json()


def test_document_crud_with_revision_and_soft_delete(client: TestClient) -> None:
    project = create_project(client)
    doc = create_document(client, project["id"])

    fetched = client.get(f"/api/v1/documents/{doc['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["title"] == "人物设定·沈亦"
    assert body["doc_type"] == "character_setting"
    assert body["revision"] == 1
    assert body["source_hash"]

    listed = client.get(f"/api/v1/projects/{project['id']}/documents").json()
    assert [d["id"] for d in listed] == [doc["id"]]

    # doc_type filter
    only_worldview = client.get(
        f"/api/v1/projects/{project['id']}/documents", params={"doc_type": "worldview"}
    ).json()
    assert only_worldview == []

    updated = client.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"revision": 1, "patch": {"title": "人物设定·沈亦（v2）", "content": "沈亦：黑色长发。"}},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "人物设定·沈亦（v2）"
    assert body["revision"] == 2

    stale = client.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"revision": 1, "patch": {"title": "覆盖"}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"

    deleted = client.delete(f"/api/v1/documents/{doc['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/documents/{doc['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/documents").json() == []


def test_document_doc_type_validation(client: TestClient) -> None:
    project = create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project['id']}/documents",
        json={"doc_type": "not_a_type", "title": "非法类型"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    listed = client.get(f"/api/v1/projects/{project['id']}/documents").json()
    assert listed == []


def test_document_entity_link_validation(client: TestClient) -> None:
    project = create_project(client)
    other = create_project(client, "另一个项目")
    foreign_character = client.post(
        f"/api/v1/projects/{other['id']}/characters", json={"name": "别家角色"}
    ).json()

    # nonexistent character → 404
    resp = client.post(
        f"/api/v1/projects/{project['id']}/documents",
        json={"doc_type": "character_setting", "title": "缺角色", "content": "x", "character_id": "nope"},
    )
    assert resp.status_code == 404

    # character from another project → 422
    resp = client.post(
        f"/api/v1/projects/{project['id']}/documents",
        json={
            "doc_type": "character_setting",
            "title": "跨项目",
            "content": "x",
            "character_id": foreign_character["id"],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_document_source_hash_recomputes_on_content_change(client: TestClient) -> None:
    project = create_project(client)
    doc = create_document(client, project["id"])
    first_hash = doc["source_hash"]
    assert first_hash

    updated = client.patch(
        f"/api/v1/documents/{doc['id']}",
        json={"revision": 1, "patch": {"content": "沈亦：黑色长发，戴银耳钉。"}},
    )
    body = updated.json()
    assert body["source_hash"] != first_hash


def test_analysis_injects_document_digest_into_key(client: TestClient) -> None:
    """DOC-004: the analysis idempotency key (snapshot source_hash) depends on the
    project's setting documents — a changed document changes the key, forcing
    re-analysis (and expiring old P2-E1-T01 snapshots)."""
    project_id, episode_id = create_episode_with_source(client)

    preview1 = client.post(f"/api/v1/episodes/{episode_id}/analyze/preview").json()
    assert preview1["source_hash"]

    create_document(client, project_id, doc_type="worldview", title="世界观", content="这个世界没有魔法，篮球即信仰。")

    preview2 = client.post(f"/api/v1/episodes/{episode_id}/analyze/preview").json()
    assert preview2["source_hash"] != preview1["source_hash"]
