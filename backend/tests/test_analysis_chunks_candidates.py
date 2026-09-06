"""P2-E1-T02 — 长文本分块 + 透明度 + 角色候选决策。

验收（phase-2-core-product P2-E1-T02）：
- 超阈值不静默截断：preview 返回 source_chars/analyzed_chars/chunk_count/
  llm_calls/max_chars；超上限（24000 字）422 并提示分集，不落快照。
- 分块失败可重试且最终一致：某块失败 → 整个 preview 失败、零快照落库；
  重试同一原文 → 相同分块与合并编号。
- 角色候选可审阅：preview 返回候选 + 同名合并建议；决策接口逐项
  create/merge/skip，重名 create 冲突、跨项目 merge 拒绝、未知名失败。
- 替换原文控件：导入落编辑器、经保存进入 Project State（见前端测试；
  后端 PATCH 语义由 test_episode_scene_crud 覆盖）。

FakeLLM 确定性：块数/合并编号/候选内容可断言，无需真实模型。
"""

from fastapi.testclient import TestClient

from tests.test_script_planning import NOVEL_TEXT, create_episode_with_source

CHUNK = 6000
MAX_CHARS = 24000


def _long_text(chars: int) -> str:
    paras = []
    i = 0
    while sum(len(p) + 1 for p in paras) < chars:
        paras.append(f"第{i}段。" + "夜色下人物推进冲突，" * 8)
        i += 1
    return "\n".join(paras)


def _preview(client: TestClient, episode_id: str):
    return client.post(f"/api/v1/episodes/{episode_id}/analyze/preview")


def _make_episode(client: TestClient, source: str) -> tuple[str, str]:
    project = client.post("/api/v1/projects", json={"name": "分块"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes",
        json={"title": "长", "source_text": source},
    ).json()
    return project["id"], episode["id"]


def test_preview_reports_scope_and_cost(client: TestClient) -> None:
    """AC1: 单块文本也返回完整范围/成本字段（analyzed == source）。"""
    _, episode_id = create_episode_with_source(client)
    body = _preview(client, episode_id).json()
    assert body["source_chars"] == len(NOVEL_TEXT)
    assert body["analyzed_chars"] == len(NOVEL_TEXT)
    assert body["chunk_count"] == 1
    assert body["llm_calls"] == 2  # 1 scene call + 1 candidate call
    assert body["max_chars"] == MAX_CHARS
    assert len(body["character_candidates"]) == 2


def test_long_text_chunked_merged_renumbered(client: TestClient) -> None:
    """AC1/AC2: 13k 字 → 3 块全分析，场景全局重编号 1..N，无截断。"""
    _, episode_id = _make_episode(client, _long_text(13000))
    resp = _preview(client, episode_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chunk_count"] == 3
    assert body["analyzed_chars"] == body["source_chars"] > 2 * CHUNK
    assert body["llm_calls"] == 4
    numbers = [p["scene_number"] for p in body["plans"]]
    assert numbers == list(range(1, len(numbers) + 1))
    assert len(numbers) >= 6  # 每块 ≥2 场景


def test_over_limit_refused_without_snapshot(client: TestClient) -> None:
    """AC1: 超 24000 字 → 422 + 分集提示，不落快照。"""
    _, episode_id = _make_episode(client, _long_text(MAX_CHARS + 100))
    resp = _preview(client, episode_id)
    assert resp.status_code == 422, resp.status_code
    assert "多集" in resp.json()["error"]["message"]
    latest = client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json()
    assert latest is None


def test_chunk_failure_persists_nothing(client: TestClient, monkeypatch) -> None:
    """AC2: 第二块失败 → preview 失败且零快照；重试一致。

    NOTE: chunk 异常经 unhandled handler 走 500 信封（500 永不回显内部细节，
    见 test_errors.py）；TestClient 默认 raise_server_exceptions=True 会直接抛
    出，这里断言异常内容 + 零落库 + 重试一致。
    """
    import pytest

    from app.llm.fake import FakeLLMGateway

    _, episode_id = _make_episode(client, _long_text(13000))
    calls = {"n": 0}
    original = FakeLLMGateway.structured_list

    async def flaky(self, schema, system, prompt):
        from app.domain.analysis import ScenePlan

        calls["n"] += 1
        if schema is ScenePlan and calls["n"] == 2:
            raise RuntimeError("boom on chunk 2")
        return await original(self, schema, system, prompt)

    monkeypatch.setattr(FakeLLMGateway, "structured_list", flaky)
    with pytest.raises(RuntimeError, match="2/3"):
        _preview(client, episode_id)
    assert client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json() is None

    monkeypatch.undo()
    retry = _preview(client, episode_id)
    assert retry.status_code == 200, retry.text
    assert retry.json()["chunk_count"] == 3


def _decide(client: TestClient, episode_id: str, snapshot_id: str, decisions: list) -> dict:
    resp = client.post(
        f"/api/v1/episodes/{episode_id}/analyze/characters",
        json={"snapshot_id": snapshot_id, "decisions": decisions},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_character_decisions_create_skip_and_conflict(client: TestClient) -> None:
    """AC3: 新建 + 忽略 + 重名新建冲突（逐项结果，整体仍 200）。"""
    project_id, episode_id = create_episode_with_source(client)
    preview = _preview(client, episode_id).json()
    names = [c["name"] for c in preview["character_candidates"]]
    assert len(names) == 2
    assert all(c["existing_character_id"] is None for c in preview["character_candidates"])

    done = _decide(client, episode_id, preview["snapshot_id"], [
        {"name": names[0], "action": "create"},
        {"name": names[1], "action": "skip"},
    ])
    by_name = {r["name"]: r for r in done["results"]}
    assert by_name[names[0]]["status"] == "created"
    assert by_name[names[0]]["character_id"]
    assert by_name[names[1]]["status"] == "skipped"

    characters = client.get(f"/api/v1/projects/{project_id}/characters").json()
    created = next(c for c in characters if c["name"] == names[0])
    assert created["appearance"]  # 候选描述回填

    # 同名再新建 → conflict 条目（不抛 409，由调用方引导合并/忽略）。
    again = _decide(client, episode_id, preview["snapshot_id"], [
        {"name": names[0], "action": "create"},
    ])
    assert again["results"][0]["status"] == "conflict"
    assert again["results"][0]["character_id"] == created["id"]


def test_character_merge_backfills_empty_appearance(client: TestClient) -> None:
    """AC3: 合并同名人物，空 appearance 由候选描述回填。"""
    project_id, episode_id = create_episode_with_source(client)
    preview = _preview(client, episode_id).json()
    name = preview["character_candidates"][0]["name"]

    existing = client.post(
        f"/api/v1/projects/{project_id}/characters", json={"name": name}
    ).json()
    assert existing["appearance"] is None

    preview2 = _preview(client, episode_id).json()
    suggestion = next(c for c in preview2["character_candidates"] if c["name"] == name)
    assert suggestion["existing_character_id"] == existing["id"]

    done = _decide(client, episode_id, preview2["snapshot_id"], [
        {"name": name, "action": "merge", "character_id": existing["id"]},
    ])
    assert done["results"][0]["status"] == "merged"
    merged = client.get(f"/api/v1/characters/{existing['id']}").json()
    assert merged["appearance"]


def test_character_decisions_reject_bad_refs(client: TestClient) -> None:
    """AC3: 未知候选名 / 跨项目 merge / 无 id merge 均为条目级 failed。"""
    _, episode_id = create_episode_with_source(client)
    other_project = client.post("/api/v1/projects", json={"name": "他山"}).json()
    outsider = client.post(
        f"/api/v1/projects/{other_project['id']}/characters", json={"name": "外人"}
    ).json()
    preview = _preview(client, episode_id).json()
    name = preview["character_candidates"][0]["name"]

    done = _decide(client, episode_id, preview["snapshot_id"], [
        {"name": "不存在的人", "action": "create"},
        {"name": name, "action": "merge", "character_id": outsider["id"]},
        {"name": name, "action": "merge"},
    ])
    statuses = [r["status"] for r in done["results"]]
    assert statuses == ["failed", "failed", "failed"]


def test_latest_snapshot_rehydrates_candidates_and_scope(client: TestClient) -> None:
    """刷新水合：latest 返回候选 + 范围计数（与 preview 一致）。"""
    _, episode_id = create_episode_with_source(client)
    preview = _preview(client, episode_id).json()
    latest = client.get(f"/api/v1/episodes/{episode_id}/analysis-snapshots/latest").json()
    assert latest["character_candidates"] == preview["character_candidates"]
    assert latest["chunk_count"] == preview["chunk_count"] == 1
    assert latest["source_chars"] == preview["source_chars"]
    assert latest["max_chars"] == MAX_CHARS
