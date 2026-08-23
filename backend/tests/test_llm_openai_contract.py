"""TASK-009 — openai 路径契约测试：在 HTTP 层 mock OpenAI `/chat/completions`。

背景：`LangChainOpenAIGateway` 是 Studio 接真实 LLM 的默认实现（backend-architecture §17/§53）。
报告定位其为「零测试 / 未验证」的 P1 缺口。本文件用 `httpx.MockTransport` 挂在
ChatOpenAI 底层 AsyncClient 上，**不发起任何真实网络请求**，覆盖：

- `structured()`  成功解析真实 Pydantic schema（ScenePlan / ShotPlan）
- `structured()`  返回无效 JSON → ProviderUnavailableError
- `structured()`  HTTP 非 200 → ProviderUnavailableError
- `structured()`  传输异常 → ProviderUnavailableError（且第三方错误被包装，业务语义不变）
- `invoke()`      普通文本补全解析
- `structured_list()`  列表容器展开

可执行：`cd backend && .\\.venv\\Scripts\\python.exe -m pytest tests/test_llm_openai_contract.py -q`
无需真实 API key，CI/本地均能运行。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.errors import ProviderUnavailableError
from app.domain.analysis import ScenePlan, ShotPlan
from app.llm.langchain_gateway import LangChainOpenAIGateway

CHAT_PATH = "/chat/completions"


# --- helpers ---------------------------------------------------------------


def _mock_chat(handler: Callable[[httpx.Request], httpx.Response], model: str = "probe"):
    """Build a real ChatOpenAI whose底层 AsyncClient walks through MockTransport.

    与 test_comfyui_client 同一思路：HTTP 层注入 transport。langchain_openai 的
    `http_async_client` 参数会把该 httpx client 透传给底层 `openai.AsyncOpenAI`，
    从而让 `chat.completions.create` 的所有请求落到 handler（base.py:1324-1344）。
    """
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        base_url="http://llm.mock:1",
        api_key="test-key-not-needed",
        temperature=0.7,
        timeout=30,
        http_async_client=http_client,
    )


def _gateway(handler: Callable[[httpx.Request], httpx.Response]) -> LangChainOpenAIGateway:
    """Attach a MockTransport-backed ChatOpenAI to an otherwise real gateway instance.

    跳过 __init__（它要求真实 base_url 且会记录日志），直接注入 `_chat`。
    """
    g = LangChainOpenAIGateway.__new__(LangChainOpenAIGateway)
    g._chat = _mock_chat(handler)
    return g


def _completion(content: str, **extra: Any) -> httpx.Response:
    payload = {
        "id": "chatcmpl_test",
        "object": "chat.completion",
        "created": 1,
        "model": "probe",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    payload.update(extra)
    return httpx.Response(200, json=payload)


def _record_calls(handler: Callable[[httpx.Request], httpx.Response]) -> tuple[list[dict], Callable]:
    seen: list[dict] = []

    def wrapper(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        seen.append(
            {
                "url": str(request.url),
                "path": request.url.path,
                "method": request.method,
                "body": body,
            }
        )
        return handler(request)

    return seen, wrapper


def _run(coro):
    return asyncio.run(coro)


# --- structured(): 成功解析 -------------------------------------------------


def test_structured_parses_scene_plan() -> None:
    scene = ScenePlan(
        scene_number=1, title="天台", location="城市天台", time="night", description="对峙", mood="tense"
    )
    handler = lambda req: _completion(json.dumps(scene.model_dump()))  # noqa: E731
    g = _gateway(handler)
    result = _run(g.structured(ScenePlan, "你是编剧", "分析这段"))
    assert isinstance(result, ScenePlan)
    assert result.title == "天台"
    assert result.location == "城市天台"
    assert result.time == "night"
    assert result.mood == "tense"


def test_structured_parses_shot_plan_with_enum() -> None:
    shot = ShotPlan(
        shot_number=1, shot_type="close_up", camera_angle="eye_level", duration=2.5, action="关键动作"
    )
    handler = lambda req: _completion(json.dumps(shot.model_dump()))  # noqa: E731
    g = _gateway(handler)
    result = _run(g.structured(ShotPlan, "你是导演", "规划分镜"))
    assert isinstance(result, ShotPlan)
    assert result.shot_type == "close_up"
    assert result.duration == 2.5


# --- structured(): 失败分支 -------------------------------------------------


def test_structured_invalid_json_raises_provider_unavailable() -> None:
    handler = lambda req: _completion("这不是 JSON {{{{")  # noqa: E731
    g = _gateway(handler)
    with pytest.raises(ProviderUnavailableError):
        _run(g.structured(ScenePlan, "sys", "prompt"))


def test_structured_non_200_raises_provider_unavailable() -> None:
    handler = lambda req: httpx.Response(429, json={"error": {"message": "rate limited"}})  # noqa: E731
    g = _gateway(handler)
    with pytest.raises(ProviderUnavailableError) as ei:
        _run(g.structured(ScenePlan, "sys", "prompt"))
    assert "failed" in str(ei.value)


def test_structured_transport_error_raises_provider_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route to model")

    g = _gateway(handler)
    with pytest.raises(ProviderUnavailableError):
        _run(g.structured(ScenePlan, "sys", "prompt"))


# --- invoke(): 普通补全 ------------------------------------------------------


def test_invoke_returns_text() -> None:
    seen, handler = _record_calls(lambda req: _completion("hello from mock"))
    g = _gateway(handler)
    out = _run(g.invoke("系统", "你好"))
    assert out == "hello from mock"
    assert seen and seen[0]["path"] == CHAT_PATH


def test_invoke_uses_single_chat_completion_hit() -> None:
    """invoke 走与 structured 相同的 /chat/completions 端点，一次调用落库一条消息。"""
    seen, handler = _record_calls(lambda req: _completion("ok"))
    g = _gateway(handler)
    _run(g.invoke("sys", "prompt"))
    assert len(seen) == 1
    body = seen[0]["body"]
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][-1]["role"] == "user"


# --- structured_list(): 列表容器 ---------------------------------------------


def test_structured_list_returns_items() -> None:
    plans = [
        ScenePlan(scene_number=1, title="A", location="L1", time="day", description="d1"),
        ScenePlan(scene_number=2, title="B", location="L2", time="night", description="d2"),
    ]
    # structured_list 传入的是 ListContainer(items=[...]) —— content 须是 `{"items": [...]}` 对象
    handler = lambda req: _completion(  # noqa: E731
        json.dumps({"items": [p.model_dump() for p in plans]})
    )
    g = _gateway(handler)
    out = _run(g.structured_list(ScenePlan, "sys", "prompt"))
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0].title == "A"
    assert out[1].title == "B"
