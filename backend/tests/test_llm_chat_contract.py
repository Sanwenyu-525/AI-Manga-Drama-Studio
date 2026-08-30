"""chat() 消息化契约测试 — LLMGateway 的 message-shaped 核心接口。

`chat()` 是 gateway 的消息形状核心（多轮对话进出 + token usage 出），为生产对话 /
记忆等 surface 打底。本文件复用 test_llm_openai_contract 的 MockTransport 思路：
HTTP 层注入 transport，不发真实请求。覆盖：

- FakeLLMGateway.chat()  确定性输出 + usage 统计 + invoke 一致性
- LangChainOpenAIGateway.chat()  多轮消息按角色落请求体（system/user/assistant）
- chat(options)  temperature / max_tokens 透传到请求体
- chat()  usage 解析（OpenAI prompt_tokens/completion_tokens → TokenUsage）
- chat()  传输异常 → ProviderUnavailableError（与 invoke 同一语义）
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from app.core.errors import ProviderUnavailableError
from app.llm.fake import FakeLLMGateway
from app.llm.langchain_gateway import LangChainOpenAIGateway
from app.llm.messages import ChatMessage, ChatOptions


def _record_calls(handler: Callable[[httpx.Request], httpx.Response]) -> tuple[list[dict], Callable]:
    seen: list[dict] = []

    def wrapper(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "body": json.loads(request.read())})
        return handler(request)

    return seen, wrapper


def _completion(content: str, **extra: object) -> httpx.Response:
    payload: dict = {
        "id": "chatcmpl_test",
        "object": "chat.completion",
        "created": 1,
        "model": "probe-model",
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


def _gateway(handler: Callable[[httpx.Request], httpx.Response]) -> LangChainOpenAIGateway:
    """MockTransport 直连底层 AsyncClient（跳过 __init__，不发真实请求）。"""
    transport = httpx.MockTransport(handler)
    from langchain_openai import ChatOpenAI

    g = LangChainOpenAIGateway.__new__(LangChainOpenAIGateway)
    g._chat = ChatOpenAI(
        model="probe",
        base_url="http://llm.mock:1",
        api_key="test-key-not-needed",
        http_async_client=httpx.AsyncClient(transport=transport),
    )
    g._base_url = "http://llm.mock:1"
    return g


def _run(coro):
    return asyncio.run(coro)


# --- Fake -------------------------------------------------------------------


def test_fake_chat_returns_contract_response() -> None:
    g = FakeLLMGateway()
    resp = _run(
        g.chat(
            [
                ChatMessage(role="system", content="你是导演"),
                ChatMessage(role="user", content="把镜头改成近景"),
            ]
        )
    )
    assert resp.content.startswith("FAKE:")
    assert "把镜头改成近景" in resp.content
    assert resp.model == "fake-chat"
    assert resp.finish_reason == "stop"
    assert resp.usage is not None
    assert resp.usage.input_tokens == len("你是导演") + len("把镜头改成近景")
    assert resp.usage.output_tokens == len(resp.content)


def test_fake_chat_multiturn_uses_last_user_turn() -> None:
    g = FakeLLMGateway()
    resp = _run(
        g.chat(
            [
                ChatMessage(role="user", content="第一轮"),
                ChatMessage(role="assistant", content="FAKE: 第一轮…"),
                ChatMessage(role="user", content="第二轮"),
            ]
        )
    )
    assert "第二轮" in resp.content
    assert "第一轮" not in resp.content.replace("FAKE: ", "")  # 只回显最后一条 user


def test_fake_chat_invoke_consistency() -> None:
    g = FakeLLMGateway()
    assert _run(g.invoke("sys", "hello")) == _run(
        g.chat(
            [ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hello")]
        )
    ).content


# --- LangChainOpenAIGateway --------------------------------------------------


def test_langchain_chat_multiturn_roles_in_request_body() -> None:
    seen, handler = _record_calls(lambda req: _completion("收到"))
    g = _gateway(handler)
    resp = _run(
        g.chat(
            [
                ChatMessage(role="system", content="s"),
                ChatMessage(role="user", content="u1"),
                ChatMessage(role="assistant", content="a1"),
                ChatMessage(role="user", content="u2"),
            ]
        )
    )
    assert resp.content == "收到"
    assert seen and seen[0]["path"] == "/chat/completions"
    roles = [m["role"] for m in seen[0]["body"]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert seen[0]["body"]["messages"][-1]["content"] == "u2"


def test_langchain_chat_parses_usage_and_model() -> None:
    handler = lambda req: _completion(  # noqa: E731
        "ok",
        usage={"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
    )
    g = _gateway(handler)
    resp = _run(g.chat([ChatMessage(role="user", content="hi")]))
    assert resp.model == "probe-model"
    assert resp.finish_reason == "stop"
    assert resp.usage is not None
    assert resp.usage.input_tokens == 12
    assert resp.usage.output_tokens == 7


def test_langchain_chat_options_reach_request_body() -> None:
    seen, handler = _record_calls(lambda req: _completion("ok"))
    g = _gateway(handler)
    _run(
        g.chat(
            [ChatMessage(role="user", content="hi")],
            options=ChatOptions(temperature=0.2, max_tokens=50),
        )
    )
    body = seen[0]["body"]
    assert body["temperature"] == 0.2
    # 新版 langchain_openai 会把 max_tokens 规范化为 max_completion_tokens
    assert body.get("max_tokens", body.get("max_completion_tokens")) == 50


def test_langchain_chat_transport_error_wraps_as_provider_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route to model")

    g = _gateway(handler)
    with pytest.raises(ProviderUnavailableError):
        _run(g.chat([ChatMessage(role="user", content="hi")]))


def test_langchain_chat_without_usage_yields_none() -> None:
    g = _gateway(lambda req: _completion("ok"))  # 无 usage 字段
    resp = _run(g.chat([ChatMessage(role="user", content="hi")]))
    assert resp.usage is None
