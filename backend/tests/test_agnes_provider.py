"""TASK-010 — AgnesImageProvider 契约测试：在 HTTP 层 mock Agnes `/images/generations`。

用 httpx.MockTransport 换掉 provider 内部的 httpx.Client 绑定（与 test_comfyui_client
同一模式），**不发起真实网络请求**。覆盖：

- generate():  无 key → ProviderUnavailableError（启动不炸，使用时报）
- generate():  成功 → POST /images/generations + 下载 URL → 落盘 + ImageResult
- generate():  HTTP 非 200 → ProviderUnavailableError
- generate():  传输异常 → ProviderUnavailableError
- generate():  响应无 data / items 空 / 无 url → ProviderUnavailableError
- cancel():    best-effort 永不抛
- probe():     无 key → connected=False + key_set=False（不抛）
- probe():     GET /models 成功 → connected=True + 模型列表/延迟
- probe():     401 / 传输异常 → connected=False + error（不抛）
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import ProviderUnavailableError
from app.providers.image.agnes import AgnesImageProvider
from app.providers.image import agnes as agnes_module

BASE = "http://agnes.mock/v1"


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 96), (90, 140, 60)).save(buf, "PNG")
    return buf.getvalue()


def _make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    monkeypatch: pytest.MonkeyPatch,
    api_key: str = "sk-test",
) -> AgnesImageProvider:
    """Build an AgnesImageProvider whose module httpx.Client goes through MockTransport."""
    transport = httpx.MockTransport(handler)

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return httpx.Client(*args, **kwargs)

    shim = SimpleNamespace(
        Client=_client_factory,
        HTTPStatusError=httpx.HTTPStatusError,
        TransportError=httpx.TransportError,
    )
    monkeypatch.setattr(agnes_module, "httpx", shim)
    return AgnesImageProvider(api_key=api_key, base_url=BASE)


def test_generate_requires_key() -> None:
    provider = AgnesImageProvider(api_key="", base_url=BASE)
    from app.providers.image.base import ImageRequest

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            provider.generate(
                ImageRequest(prompt="manga, cyberpunk alley"), lambda p, s: None
            )
        )


def test_generate_success_downloads_image(tmp_path, monkeypatch) -> None:
    png = _png_bytes()
    posted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/images/generations":
            posted.append({"path": request.url.path, "body": __import__("json").loads(request.read())})
            return httpx.Response(
                200,
                json={
                    "data": [{"url": "http://agnes.mock/out.png", "revised_prompt": "x"}],
                },
            )
        if request.url.path == "/out.png":
            return httpx.Response(200, content=png)
        return httpx.Response(404)

    provider = _make_provider(handler, monkeypatch)
    from app.providers.image.base import ImageRequest

    result = asyncio.run(
        provider.generate(
            ImageRequest(prompt="manga, cyberpunk alley", width=1024, height=1536),
            lambda p, s: None,
        )
    )
    assert result.success is True
    assert result.output_path
    import pathlib

    assert pathlib.Path(result.output_path).read_bytes() == png
    assert posted and posted[0]["path"] == "/v1/images/generations"
    assert posted[0]["body"]["model"] == "agnes-image-2.1-flash"
    assert posted[0]["body"]["size"] == "1024x1536"


def test_generate_http_error_raises_provider_unavailable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = _make_provider(handler, monkeypatch)
    from app.providers.image.base import ImageRequest

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            provider.generate(
                ImageRequest(prompt="p"), lambda p, s: None
            )
        )


def test_generate_transport_error_raises_provider_unavailable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("unreachable")

    provider = _make_provider(handler, monkeypatch)
    from app.providers.image.base import ImageRequest

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.generate(ImageRequest(prompt="p"), lambda p, s: None))


def test_generate_empty_data_raises_provider_unavailable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    provider = _make_provider(handler, monkeypatch)
    from app.providers.image.base import ImageRequest

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.generate(ImageRequest(prompt="p"), lambda p, s: None))


def test_generate_missing_url_raises_provider_unavailable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"revised_prompt": "no url"}]})

    provider = _make_provider(handler, monkeypatch)
    from app.providers.image.base import ImageRequest

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.generate(ImageRequest(prompt="p"), lambda p, s: None))


def test_cancel_is_best_effort_no_raise() -> None:
    provider = AgnesImageProvider(api_key="sk-test", base_url=BASE)
    asyncio.run(provider.cancel("agnes_123"))  # must not raise


# --- probe（POST /providers/agnes/test 的底层） ------------------------


def test_probe_without_key_reports_key_set_false() -> None:
    provider = AgnesImageProvider(api_key="", base_url=BASE)
    result = asyncio.run(provider.probe())
    assert result["connected"] is False
    assert result["key_set"] is False
    assert "STUDIO_AGNES_API_KEY" in result["error"]


def test_probe_success_parses_models(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={"data": [{"id": "agnes-2.0-flash"}, {"id": "agnes-image-2.1-flash"}]},
        )

    provider = _make_provider(handler, monkeypatch)
    result = asyncio.run(provider.probe())
    assert result["connected"] is True
    assert result["key_set"] is True
    assert result["models_count"] == 2
    assert result["image_model_available"] is True
    assert result["latency_ms"] >= 0


def test_probe_http_error_never_raises(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    provider = _make_provider(handler, monkeypatch)
    result = asyncio.run(provider.probe())
    assert result["connected"] is False
    assert result["key_set"] is True
    assert "401" in result["error"]


def test_probe_transport_error_never_raises(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("unreachable")

    provider = _make_provider(handler, monkeypatch)
    result = asyncio.run(provider.probe())
    assert result["connected"] is False
    assert "unreachable" in result["error"] or "Agnes API unreachable" in result["error"]
