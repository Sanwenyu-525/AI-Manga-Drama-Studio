"""LLM runtime settings endpoints (GET/PUT /llm/config, POST /llm/test, GET /llm/models).

The service resolves env defaults overridden by an optional {data_dir}/llm.json
layer. Data-dir is isolated per test so nothing touches the real studio data.
"""

from __future__ import annotations

import app.services.llm_settings_service as svc
from app.core.errors import ProviderUnavailableError

import asyncio

import pytest


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.settings, "data_dir", tmp_path)
    # 让每个用例从干净覆盖层开始
    monkeypatch.setattr(svc, "_write", svc._write)  # keep real write into tmp dir
    (tmp_path / svc.LLM_CONFIG_FILE).write_text("{}", encoding="utf-8")


def test_get_config_defaults_fake(client):
    resp = client.get("/api/v1/llm/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] in ("fake", "openai")  # 跟随 env；无覆盖层时至少可读
    assert "api_key" not in body  # 从不回传完整 key
    assert "api_key_set" in body
    assert "model" in body


def test_update_openai_requires_base_url(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    resp = client.put("/api/v1/llm/config", json={"mode": "openai"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_update_roundtrip_masks_key(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    resp = client.put(
        "/api/v1/llm/config",
        json={
            "mode": "openai",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-secret-1234",
            "model": "deepseek-chat",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "openai"
    assert body["base_url"] == "https://api.deepseek.com"
    assert body["model"] == "deepseek-chat"
    assert body["api_key_set"] is True
    assert body["api_key_hint"] == "••••1234"
    assert "sk-secret-1234" not in str(body)  # 不泄露完整 key

    # 切回 fake 不需要 base_url
    resp = client.put("/api/v1/llm/config", json={"mode": "fake"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "fake"


def test_persisted_overrides_survive_across_calls(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put(
        "/api/v1/llm/config",
        json={"mode": "openai", "base_url": "http://127.0.0.1:11434", "model": "qwen2"},
    )
    # P-LLM-Profiles：PUT /llm/config 更新激活连接，权威源是 llm_profiles.json
    assert svc._profiles_path().exists()
    state = svc._load_state()
    active = next(p for p in state["profiles"] if p["id"] == state["active_profile_id"])
    assert active["mode"] == "openai"
    assert active["base_url"] == "http://127.0.0.1:11434"
    assert active["model"] == "qwen2"
    # 再读一致
    body = client.get("/api/v1/llm/config").json()
    assert body["model"] == "qwen2"


# --------------------------------------------------------------- test 探测 -----


def test_llm_test_fake_mode_connected(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/llm/config", json={"mode": "fake"})  # 显式锁定，不依赖 env 默认
    resp = client.post("/api/v1/llm/test", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["mode"] == "fake"


def test_llm_test_never_raises_on_dead_endpoint(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/llm/config", json={"mode": "openai", "base_url": "http://127.0.0.1:9", "model": "m"})
    resp = client.post("/api/v1/llm/test", json={})
    # 探测失败也返回 200 + connected=False（对齐 /providers/comfyui/test 形态）
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body.get("error")


def test_llm_test_accepts_unsaved_overrides(client, tmp_path, monkeypatch):
    """请求体覆盖优先于已存配置（测试未保存的连接）。"""
    _isolate(tmp_path, monkeypatch)
    captured: dict = {}

    async def fake_probe(base_url, api_key):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        return 200, ["deepseek-chat", "deepseek-reasoner"]

    monkeypatch.setattr(svc, "_probe_models", fake_probe)
    resp = client.post(
        "/api/v1/llm/test",
        json={"base_url": "https://api.example.com", "api_key": "sk-new", "model": "deepseek-chat"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["models_count"] == 2
    assert body["sample_models"][0] == "deepseek-chat"
    assert captured == {"base_url": "https://api.example.com", "api_key": "sk-new"}


def test_llm_test_auth_failure_shape(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    async def unauthorized(base_url, api_key):
        return 401, []

    monkeypatch.setattr(svc, "_probe_models", unauthorized)
    resp = client.post("/api/v1/llm/test", json={"base_url": "https://api.example.com"})
    body = resp.json()
    assert body["connected"] is False
    assert "鉴权失败" in body["error"]


# ------------------------------------------------------------ models 端点 -----


def test_llm_models_fake(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/llm/config", json={"mode": "fake"})
    resp = client.get("/api/v1/llm/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == ["fake-chat"]


def test_llm_models_openai_success(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/llm/config", json={"mode": "openai", "base_url": "https://api.example.com", "model": "m"})

    async def ok(base_url, api_key):
        return 200, ["m2", "m1"]

    monkeypatch.setattr(svc, "_probe_models", ok)
    resp = client.get("/api/v1/llm/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == ["m2", "m1"]


def test_llm_models_openai_failure_raises_503(client, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    client.put("/api/v1/llm/config", json={"mode": "openai", "base_url": "https://api.example.com", "model": "m"})

    async def bad(base_url, api_key):
        return 401, []

    monkeypatch.setattr(svc, "_probe_models", bad)
    resp = client.get("/api/v1/llm/models")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


# ------------------------------------------------------- gateway stream -------


def test_fake_gateway_stream_deltas():
    from app.llm.fake import FakeLLMGateway

    gw = FakeLLMGateway()

    async def collect():
        chunks = [chunk async for chunk in gw.stream("sys", "接近景镜头，沈亦突破上篮")]
        return chunks

    chunks = asyncio.run(collect())
    assert len(chunks) > 1
    assert "".join(chunks) == asyncio.run(gw.invoke("sys", "接近景镜头，沈亦突破上篮"))


def test_langchain_gateway_stream_with_fake_chat():
    """LangChainOpenAIGateway.stream 走 ChatOpenAI.astream —— 用 LangChain 自带
    GenericFakeChatModel 验证分片路径（不发真实请求，不重复造测试桩）。"""
    from langchain_core.language_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from app.llm.langchain_gateway import LangChainOpenAIGateway

    gw = LangChainOpenAIGateway.__new__(LangChainOpenAIGateway)  # 跳过 __init__（不建真实 client）
    gw._chat = GenericFakeChatModel(messages=iter([AIMessage(content="你好，导演。")]))
    gw._base_url = "http://fake"

    async def collect():
        return [chunk async for chunk in gw.stream("sys", "hi")]

    chunks = asyncio.run(collect())
    assert "".join(chunks) == "你好，导演。"


@pytest.mark.parametrize("missing", ["base_url"])
def test_openai_gateway_requires_base_url(missing):
    from app.llm.langchain_gateway import LangChainOpenAIGateway

    with pytest.raises(ProviderUnavailableError):
        LangChainOpenAIGateway(base_url=None if missing == "base_url" else "x", api_key=None, model="m")
