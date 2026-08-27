"""Project prompt library tests — 可编辑预设库（target_type=PROJECT）。

覆盖：创建项目级预设 → 列表带 active 内容 → 新增不可变版本并自动置为当前 →
激活旧版本 → 删除（连同版本）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _project(client: TestClient) -> dict:
    return client.post("/api/v1/projects", json={"name": "提示词库测试"}).json()


def test_project_prompt_preset_crud(client: TestClient) -> None:
    project = _project(client)
    pid = project["id"]

    # 初始为空
    assert client.get(f"/api/v1/projects/{pid}/prompts").json() == []

    # 创建 v1
    created = client.post(
        f"/api/v1/projects/{pid}/prompts",
        json={"prompt_type": "CUSTOM", "positive_prompt": "赛博都市 夜景 霓虹"},
    )
    assert created.status_code == 201
    preset_id = created.json()["prompt_id"]

    listed = client.get(f"/api/v1/projects/{pid}/prompts").json()
    assert len(listed) == 1
    item = listed[0]
    assert item["id"] == preset_id
    assert item["target_type"] == "PROJECT"
    assert item["active_positive_prompt"] == "赛博都市 夜景 霓虹"
    assert item["versions_count"] == 1

    # 新增 v2（不可变版本，自动置为当前）
    v2 = client.post(
        f"/api/v1/prompts/{preset_id}/versions",
        json={"positive_prompt": "赛博都市 夜景 淫雨 霓虹 反射", "negative_prompt": "模糊 过曝"},
    )
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2

    listed = client.get(f"/api/v1/projects/{pid}/prompts").json()
    assert listed[0]["active_positive_prompt"] == "赛博都市 夜景 淫雨 霓虹 反射"
    assert listed[0]["active_negative_prompt"] == "模糊 过曝"
    assert listed[0]["versions_count"] == 2

    # 激活旧版本 v1
    versions = client.get(f"/api/v1/prompts/{preset_id}/versions").json()
    v1 = next(v for v in versions if v["version_number"] == 1)
    active = client.post(f"/api/v1/prompts/{preset_id}/versions/{v1['id']}/activate").json()
    assert active["is_active"] is True

    # 删除（连同版本）
    deleted = client.delete(f"/api/v1/prompts/{preset_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/prompts").json() == []
    # 提示词不存在 → 404
    assert client.get(f"/api/v1/prompts/{preset_id}/versions").status_code == 404


def test_project_prompt_preset_rejects_missing_project(client: TestClient) -> None:
    assert client.get("/api/v1/projects/does-not-exist/prompts").status_code == 404
    assert client.post("/api/v1/projects/does-not-exist/prompts", json={"positive_prompt": "x"}).status_code == 404
