"""LLM 多连接 Profile Registry + 任务绑定 + 能力标记（P-LLM-Profiles）。

覆盖：
- GET /llm/profiles            首次播种（env/llm.json → 默认连接）+ tasks/ bindings 形状
- POST /llm/profiles           创建（openai 无 base_url → 422）
- POST .../activate            切换激活连接 → GET /llm/config 跟随
- PATCH /llm/profiles/{id}     局部更新 + api_key 掩码不回显
- DELETE /llm/profiles/{id}    激活连接禁删；删除后绑定一并清除
- PUT /llm/task-bindings       任务绑定（未知任务/连接 → 422；None 解绑）
- factory.create_gateway(task) 任务解析：绑定优先，未绑定跟随激活；同配置共享实例
- capabilities                 模型名启发式 + override 优先 + fake 全 False
"""

from __future__ import annotations

import asyncio

import pytest

import app.llm.factory as llm_factory
import app.services.llm_settings_service as svc


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Isolated data_dir + clean factory cache per test."""
    monkeypatch.setattr(svc.settings, "data_dir", tmp_path)
    (tmp_path / svc.LLM_CONFIG_FILE).write_text("{}", encoding="utf-8")
    llm_factory.reset_gateway()
    yield tmp_path
    llm_factory.reset_gateway()


def _create(client, name: str, **fields) -> dict:
    resp = client.post("/api/v1/llm/profiles", json={"name": name, **fields})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ------------------------------------------------------------------ 列表/播种 --


def test_profiles_seeded_from_legacy_layer(client, isolated):
    resp = client.get("/api/v1/llm/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_profile_id"] == "default"
    assert len(body["profiles"]) == 1
    seed = body["profiles"][0]
    assert seed["id"] == "default"
    assert seed["name"] == "默认连接"
    assert seed["is_active"] is True
    assert seed["bound_tasks"] == []
    assert {"id", "label"} == set(body["tasks"][0].keys())
    assert {t["id"] for t in body["tasks"]} == {"director", "script", "continuity"}
    # 播种只建视图，不落盘 —— 直到第一次变更
    assert not svc._profiles_path().exists()


def test_profile_read_never_echoes_api_key(client, isolated):
    created = _create(
        client,
        "deepseek",
        mode="openai",
        base_url="https://api.deepseek.com",
        api_key="sk-secret-9876",
        model="deepseek-chat",
    )
    assert created["api_key_set"] is True
    assert created["api_key_hint"] == "••••9876"
    assert "sk-secret-9876" not in str(created)


# ---------------------------------------------------------------------- 创建 --


def test_create_openai_profile_requires_base_url(client, isolated):
    resp = client.post("/api/v1/llm/profiles", json={"name": "bad", "mode": "openai"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_profile_and_list(client, isolated):
    _create(
        client,
        "本地 qwen",
        mode="openai",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3",
    )
    body = client.get("/api/v1/llm/profiles").json()
    assert len(body["profiles"]) == 2
    assert body["profiles"][1]["name"] == "本地 qwen"
    assert body["profiles"][1]["is_active"] is False
    # 变更已落盘，重启视角再读一致
    state = svc._load_state()
    assert len(state["profiles"]) == 2


# ---------------------------------------------------------------- 切换/更新 --


def test_activate_switches_effective_config(client, isolated):
    created = _create(
        client,
        "deepseek",
        mode="openai",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    resp = client.post(f"/api/v1/llm/profiles/{created['id']}/activate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    cfg = client.get("/api/v1/llm/config").json()
    assert cfg["profile_id"] == created["id"]
    assert cfg["mode"] == "openai"
    assert cfg["base_url"] == "https://api.deepseek.com"


def test_legacy_put_updates_active_profile_only(client, isolated):
    second = _create(client, "第二连接", mode="fake")
    client.post(f"/api/v1/llm/profiles/{second['id']}/activate")

    resp = client.put(
        "/api/v1/llm/config",
        json={"mode": "openai", "base_url": "http://10.0.0.5:8000/v1", "model": "m1"},
    )
    assert resp.status_code == 200
    # 激活连接（第二连接）被更新，默认连接不受影响
    body = client.get("/api/v1/llm/profiles").json()
    by_name = {p["name"]: p for p in body["profiles"]}
    assert by_name["第二连接"]["base_url"] == "http://10.0.0.5:8000/v1"
    assert by_name["默认连接"]["mode"] in ("fake", "openai")  # 未被 PUT 波及即可
    assert by_name["第二连接"]["is_active"] is True


def test_patch_profile_and_key_hint(client, isolated):
    created = _create(
        client,
        "lm studio",
        mode="openai",
        base_url="http://127.0.0.1:1234/v1",
        api_key="sk-old-1111",
    )
    resp = client.patch(
        f"/api/v1/llm/profiles/{created['id']}", json={"model": "qwen2.5-7b", "api_key": "sk-new-2222"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "qwen2.5-7b"
    assert body["api_key_hint"] == "••••2222"
    # base_url 未动
    assert body["base_url"] == "http://127.0.0.1:1234/v1"


def test_patch_missing_profile_404(client, isolated):
    resp = client.patch("/api/v1/llm/profiles/prof_nope", json={"model": "x"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"


# ---------------------------------------------------------------------- 删除 --


def test_delete_active_profile_forbidden(client, isolated):
    resp = client.delete("/api/v1/llm/profiles/default")
    assert resp.status_code == 422
    body = client.get("/api/v1/llm/profiles").json()
    assert len(body["profiles"]) == 1


def test_delete_profile_cleans_bindings(client, isolated):
    target = _create(
        client,
        "director 专用",
        mode="openai",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3",
    )
    resp = client.put("/api/v1/llm/task-bindings", json={"bindings": {"director": target["id"]}})
    assert resp.status_code == 200
    assert resp.json()["task_bindings"]["director"]["profile_id"] == target["id"]

    resp = client.delete(f"/api/v1/llm/profiles/{target['id']}")
    assert resp.status_code == 200
    body = client.get("/api/v1/llm/profiles").json()
    assert all(p["id"] != target["id"] for p in body["profiles"])
    assert body["task_bindings"]["director"] is None  # 绑定随连接删除一并清除


# ------------------------------------------------------------------ 任务绑定 --


def test_task_bindings_validate_task_and_profile(client, isolated):
    resp = client.put("/api/v1/llm/task-bindings", json={"bindings": {"unknown_task": "default"}})
    assert resp.status_code == 422
    resp = client.put("/api/v1/llm/task-bindings", json={"bindings": {"director": "prof_missing"}})
    assert resp.status_code == 422


def test_task_bindings_and_factory_resolution(client, isolated):
    local = _create(
        client,
        "本地",
        mode="openai",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3",
    )
    resp = client.put(
        "/api/v1/llm/task-bindings", json={"bindings": {"director": local["id"], "script": None}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_bindings"]["director"]["profile_id"] == local["id"]
    assert body["task_bindings"]["script"] is None

    # factory：绑定任务用绑定连接（openai → LangChain 网关），未绑定跟随激活（fake）
    gw_director = llm_factory.create_gateway("director")
    gw_script = llm_factory.create_gateway("script")
    gw_default = llm_factory.create_gateway()
    from app.llm.fake import FakeLLMGateway
    from app.llm.langchain_gateway import LangChainOpenAIGateway

    assert isinstance(gw_director, LangChainOpenAIGateway)
    assert isinstance(gw_script, FakeLLMGateway)
    assert isinstance(gw_default, FakeLLMGateway)
    # 同配置共享实例
    assert llm_factory.create_gateway("script") is gw_script

    # 切换激活到另一条 fake 连接 → default/script 跟随新激活；显式绑定的 director 不动
    backup = _create(client, "备用", mode="fake")
    client.post(f"/api/v1/llm/profiles/{backup['id']}/activate")
    assert isinstance(llm_factory.create_gateway(), FakeLLMGateway)
    assert isinstance(llm_factory.create_gateway("script"), FakeLLMGateway)
    assert isinstance(llm_factory.create_gateway("director"), LangChainOpenAIGateway)


def test_unknown_task_raises_in_factory(isolated):
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        llm_factory.create_gateway("bogus")


# ---------------------------------------------------------------- 能力标记 ----


def test_capabilities_heuristics():
    from app.llm.capabilities import model_capabilities

    caps = model_capabilities("gpt-4o-mini", mode="openai")
    assert caps["vision"] is True and caps["tools"] is True

    caps = model_capabilities("deepseek-chat", mode="openai")
    assert caps["vision"] is False and caps["tools"] is True

    caps = model_capabilities("deepseek-reasoner", mode="openai")
    assert caps["tools"] is False and caps["reasoning"] is True

    caps = model_capabilities("qwen2.5:7b", mode="openai")
    assert caps == {"tools": True, "vision": False, "reasoning": False, "source": "heuristic"}


def test_capabilities_override_wins_and_fake_is_false():
    from app.llm.capabilities import model_capabilities

    caps = model_capabilities("deepseek-chat", mode="openai", override={"vision": True})
    assert caps["vision"] is True and caps["source"] == "override"

    caps = model_capabilities("anything", mode="fake")
    assert caps == {"tools": False, "vision": False, "reasoning": False, "source": "heuristic"}


def test_profile_capabilities_surfaced_in_read(client, isolated):
    created = _create(
        client,
        "glm-4v",
        mode="openai",
        base_url="http://127.0.0.1:8000/v1",
        model="glm-4v-flash",
    )
    assert created["capabilities"]["vision"] is True
    # 显式覆写优先于启发式
    resp = client.patch(
        f"/api/v1/llm/profiles/{created['id']}", json={"capabilities": {"vision": False}}
    )
    assert resp.json()["capabilities"]["vision"] is False
    assert resp.json()["capabilities"]["source"] == "override"


# ------------------------------------------------- test/models 按 profile 探测 --


def test_llm_test_targets_specific_profile(client, isolated, monkeypatch):
    target = _create(
        client,
        "远端",
        mode="openai",
        base_url="https://remote.example.com",
        api_key="sk-remote",
    )
    captured: dict = {}

    async def fake_probe(base_url, api_key, **kwargs):
        captured.update({"base_url": base_url, "api_key": api_key})
        return 200, ["m"]

    monkeypatch.setattr(svc, "_probe_models", fake_probe)
    resp = client.post("/api/v1/llm/test", json={"profile_id": target["id"]})
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert captured == {"base_url": "https://remote.example.com", "api_key": "sk-remote"}


def test_llm_test_unknown_profile_404(client, isolated):
    resp = client.post("/api/v1/llm/test", json={"profile_id": "prof_nope"})
    assert resp.status_code == 404


def test_llm_models_for_specific_profile(client, isolated, monkeypatch):
    target = _create(
        client, "ollama", mode="openai", base_url="http://127.0.0.1:11434/v1"
    )

    async def ok(base_url, api_key, **kwargs):
        return 200, ["qwen3", "llama3"]

    monkeypatch.setattr(svc, "_probe_models", ok)
    resp = client.get(f"/api/v1/llm/models?profile_id={target['id']}")
    assert resp.status_code == 200
    assert resp.json()["models"] == ["qwen3", "llama3"]


# ----------------------------------------------------- fake gateway 冒烟回归 --


def test_default_chain_still_runs_end_to_end(client, isolated):
    """播种默认连接（fake）下，经 API 依赖的 create_gateway 仍产出确定性结果。"""
    from app.llm.messages import ChatMessage

    gw = llm_factory.create_gateway()
    resp = asyncio.run(gw.chat([ChatMessage(role="user", content="冒烟")]))
    assert resp.content.startswith("FAKE:")
