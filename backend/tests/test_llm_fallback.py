"""LLM 显式降级链（P-LLM-Fallback）——「不静默掩盖模型故障」原则的落地验证。

覆盖：
- FallbackLLMGateway 单元：主连接失败 → 后备服务 + 事件宣告 + served_by 归因；
  主连接直接成功 → 无事件；全链耗尽 → ProviderUnavailableError（attempted 明细）；
  structured / stream（首片前降级）路径。
- service：set_task_fallbacks 校验（未知任务/连接 → 422；去重保序；空=清除）；
  get_task_llm_chain 语义（已绑定任务的激活连接不隐式入链；未绑定跟随激活）。
- factory：配置降级 → FallbackLLMGateway（同链共享实例）；清除 → 普通网关。
- 集成：director 绑定死端点 + 降级到 fake → chat 成功且事件已发布。
- API：PUT /llm/task-fallbacks + GET 形状；删除连接从链中剥离。
"""

from __future__ import annotations

import asyncio

import pytest

import app.llm.factory as llm_factory
import app.services.llm_settings_service as svc
from app.core.errors import ProviderUnavailableError
from app.events import bus as bus_module
from app.events.bus import EVENT_LLM_FALLBACK_USED
from app.llm.fallback import FallbackLLMGateway
from app.llm.messages import ChatMessage, ChatResponse


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.settings, "data_dir", tmp_path)
    (tmp_path / svc.LLM_CONFIG_FILE).write_text("{}", encoding="utf-8")
    llm_factory.reset_gateway()
    yield tmp_path
    llm_factory.reset_gateway()


def _create(client, name: str, **fields) -> dict:
    resp = client.post("/api/v1/llm/profiles", json={"name": name, **fields})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- 单元：FallbackLLMGateway -------------------------------------------------


class BoomGateway:
    """除 stream 外全部抛错的桩（模拟主连接故障）。"""

    async def chat(self, messages, *, options=None):
        raise ProviderUnavailableError("boom", {})

    async def invoke(self, system, prompt):
        raise ProviderUnavailableError("boom", {})

    async def structured(self, schema, system, prompt):
        raise ProviderUnavailableError("boom", {})

    async def structured_list(self, schema, system, prompt):
        raise ProviderUnavailableError("boom", {})

    async def stream(self, system, prompt):
        raise ProviderUnavailableError("boom", {})
        yield  # pragma: no cover


class OkGateway:
    """确定性服务的桩。"""

    async def chat(self, messages, *, options=None):
        return ChatResponse(content="ok", model="ok-model")

    async def invoke(self, system, prompt):
        return "ok"

    async def structured(self, schema, system, prompt):
        return schema(scene_number=1, title="t", location="l", time="day", description="d")

    async def structured_list(self, schema, system, prompt):
        return [await self.structured(schema, system, prompt)]

    async def stream(self, system, prompt):
        yield "ok-stream"


def _chain(gateways: list) -> FallbackLLMGateway:
    """把 [Boom, Ok, ...] 桩列表包成降级链；builder 按候选序号取桩。"""
    candidates = [{"profile_id": f"p{i}", "profile_name": f"P{i}", "mode": "fake"} for i in range(len(gateways))]
    mapping = dict(enumerate(gateways))
    return FallbackLLMGateway(
        task="director",
        candidates=candidates,
        builder=lambda cand: mapping[candidates.index(cand)],
    )


def _collect_events(monkeypatch) -> list:
    seen: list = []
    monkeypatch.setattr(bus_module.bus, "publish", lambda event: seen.append(event))
    return seen


def test_fallback_serves_from_backup_and_announces(monkeypatch):
    events = _collect_events(monkeypatch)
    chain = _chain([BoomGateway(), OkGateway()])
    resp = asyncio.run(chain.chat([ChatMessage(role="user", content="hi")]))

    assert resp.content == "ok"
    assert resp.served_by_profile == "p1"
    assert resp.served_by_profile_name == "P1"
    assert len(events) == 1
    event = events[0]
    assert event.event_type == EVENT_LLM_FALLBACK_USED
    assert event.payload["task"] == "director"
    assert event.payload["served_by_profile_id"] == "p1"
    assert event.payload["failed"][0]["profile_id"] == "p0"


def test_primary_success_publishes_no_event(monkeypatch):
    events = _collect_events(monkeypatch)
    chain = _chain([OkGateway()])
    resp = asyncio.run(chain.chat([ChatMessage(role="user", content="hi")]))

    assert resp.content == "ok"
    # 主连接直接服务：无降级事件，但仍有归因标注（观测用）
    assert resp.served_by_profile == "p0"
    assert events == []


def test_chain_exhaustion_raises_with_attempted_details(monkeypatch):
    _collect_events(monkeypatch)
    chain = _chain([BoomGateway(), BoomGateway()])
    with pytest.raises(ProviderUnavailableError) as ei:
        asyncio.run(chain.chat([ChatMessage(role="user", content="hi")]))

    attempted = ei.value.details.get("attempted") if hasattr(ei.value, "details") else None
    assert attempted and len(attempted) == 2
    assert attempted[0]["profile_id"] == "p0"


def test_fallback_structured_path(monkeypatch):
    _collect_events(monkeypatch)
    from app.domain.analysis import ScenePlan

    chain = _chain([BoomGateway(), OkGateway()])
    plan = asyncio.run(chain.structured(ScenePlan, "sys", "p"))
    assert isinstance(plan, ScenePlan)


def test_fallback_stream_degrades_before_first_chunk(monkeypatch):
    events = _collect_events(monkeypatch)
    chain = _chain([BoomGateway(), OkGateway()])

    async def collect():
        return [chunk async for chunk in chain.stream("sys", "p")]

    assert asyncio.run(collect()) == ["ok-stream"]
    assert len(events) == 1


def test_builder_failure_counts_as_candidate_failure(monkeypatch):
    events = _collect_events(monkeypatch)
    candidates = [
        {"profile_id": "bad", "profile_name": "Bad", "mode": "openai", "base_url": None},
        {"profile_id": "p1", "profile_name": "P1", "mode": "fake"},
    ]

    def builder(cand):
        if cand["profile_id"] == "bad":
            raise ProviderUnavailableError("缺 base_url", {})
        return OkGateway()

    chain = FallbackLLMGateway(task="director", candidates=candidates, builder=builder)
    resp = asyncio.run(chain.chat([ChatMessage(role="user", content="hi")]))
    assert resp.served_by_profile == "p1"
    assert len(events) == 1
    assert events[0].payload["failed"][0]["profile_id"] == "bad"


# --- service：链语义 ----------------------------------------------------------


def test_task_fallbacks_validation_and_ordering(client, isolated):
    a = _create(client, "A", mode="fake")
    b = _create(client, "B", mode="fake")

    resp = client.put(
        "/api/v1/llm/task-fallbacks",
        json={"fallbacks": {"unknown": [a["id"]]}},
    )
    assert resp.status_code == 422

    resp = client.put(
        "/api/v1/llm/task-fallbacks",
        json={"fallbacks": {"director": [a["id"], b["id"], a["id"]]}},
    )
    assert resp.status_code == 200
    chain_read = resp.json()["task_fallbacks"]["director"]
    assert [f["profile_id"] for f in chain_read] == [a["id"], b["id"]]  # 去重保序
    assert resp.json()["task_fallbacks"]["script"] == []

    resp = client.put(
        "/api/v1/llm/task-fallbacks",
        json={"fallbacks": {"director": ["prof_missing"]}},
    )
    assert resp.status_code == 422

    # 空列表 = 清除
    resp = client.put("/api/v1/llm/task-fallbacks", json={"fallbacks": {"director": []}})
    assert resp.json()["task_fallbacks"]["director"] == []


def test_chain_semantics_bound_task_excludes_active(isolated):
    """已绑定任务的激活连接不隐式入链 —— 链上只有用户配置过的候选。"""
    # director 绑定到 default，并把 default 设为其显式降级（应被去重）
    svc.set_task_bindings({"director": "default"})
    svc.set_task_fallbacks({"director": ["default"]})
    assert [c["profile_id"] for c in svc.get_task_llm_chain("director")] == ["default"]

    # 新建一条 fake 连接并把它设为激活：director 仍绑定 default，链不含新激活连接。
    state = svc._load_state()
    state["profiles"].append(
        {
            "id": "other",
            "name": "Other",
            "mode": "fake",
            "base_url": None,
            "api_key": None,
            "model": None,
            "capabilities": None,
            "created_at": "",
            "updated_at": "",
        }
    )
    state["active_profile_id"] = "other"
    svc._save_state(state)
    chain = svc.get_task_llm_chain("director")
    assert [c["profile_id"] for c in chain] == ["default"]  # 激活连接未隐式入链
    # script 未绑定 → 主 = 新激活连接
    assert [c["profile_id"] for c in svc.get_task_llm_chain("script")] == ["other"]


# --- factory / 集成 -----------------------------------------------------------


def test_factory_builds_chain_only_when_configured(client, isolated):
    a = _create(client, "A", mode="fake")
    b = _create(client, "B", mode="fake")

    # 无降级配置 → 普通网关
    assert not isinstance(llm_factory.create_gateway("director"), FallbackLLMGateway)

    resp = client.put(
        "/api/v1/llm/task-fallbacks",
        json={"fallbacks": {"director": [a["id"], b["id"]]}},
    )
    assert resp.status_code == 200
    chain_gw = llm_factory.create_gateway("director")
    assert isinstance(chain_gw, FallbackLLMGateway)
    # 同链共享实例；其他任务仍是普通网关
    assert llm_factory.create_gateway("director") is chain_gw
    assert not isinstance(llm_factory.create_gateway("script"), FallbackLLMGateway)

    # 清除 → 回到普通网关
    client.put("/api/v1/llm/task-fallbacks", json={"fallbacks": {"director": []}})
    assert not isinstance(llm_factory.create_gateway("director"), FallbackLLMGateway)


def test_end_to_end_failover_with_dead_primary(client, isolated, monkeypatch):
    """集成：director 绑定死端点连接 + 降级 fake → chat 成功 + 事件宣告。"""
    dead = _create(
        client,
        "死端点",
        mode="openai",
        base_url="http://127.0.0.1:9/v1",
        model="m",
    )
    client.post(f"/api/v1/llm/profiles/{dead['id']}/activate")
    events = _collect_events(monkeypatch)

    resp = client.put(
        "/api/v1/llm/task-fallbacks",
        json={"fallbacks": {"director": ["default"]}},
    )
    assert resp.status_code == 200

    gw = llm_factory.create_gateway("director")
    assert isinstance(gw, FallbackLLMGateway)
    out = asyncio.run(gw.chat([ChatMessage(role="user", content="导演指令")]))
    assert out.content.startswith("FAKE:")
    assert out.served_by_profile == "default"
    assert any(e.event_type == EVENT_LLM_FALLBACK_USED for e in events)


# --- API：删除连接从降级链剥离 -------------------------------------------------


def test_delete_profile_strips_task_fallbacks(client, isolated):
    a = _create(client, "A", mode="fake")
    b = _create(client, "B", mode="fake")
    client.put("/api/v1/llm/task-fallbacks", json={"fallbacks": {"director": [a["id"], b["id"]]}})

    resp = client.delete(f"/api/v1/llm/profiles/{a['id']}")
    assert resp.status_code == 200
    body = client.get("/api/v1/llm/profiles").json()
    assert [f["profile_id"] for f in body["task_fallbacks"]["director"]] == [b["id"]]
