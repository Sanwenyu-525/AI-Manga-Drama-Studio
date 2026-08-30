"""P4-T008 — ComfyUIClient unit tests via httpx.MockTransport (no real ComfyUI / WS).

Covers every HTTP method on ComfyUIClient: health_check, queue_prompt (success /
HTTP error -> ComfyUIError / transport error -> ProviderUnavailableError),
get_history, get_outputs, download_output, upload_image, cancel. The client opens a
fresh httpx.AsyncClient per call, so each test swaps the module's httpx binding for a
transport-injected factory. Every client method is async, so calls run through
asyncio.run (same pattern as the generation worker-driven tests). The WS monitor path
and its history fallback are exercised in test_comfyui_link (P4-T010).
"""

import asyncio
from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest

from app.core.errors import ComfyUIError, ProviderUnavailableError
from app.providers.comfyui import client as client_module
from app.providers.comfyui.client import ComfyUIClient

BASE = "http://comfy.test:8188"


@pytest.fixture()
def comfy(monkeypatch) -> Callable[[Callable, str], tuple[ComfyUIClient, httpx.MockTransport]]:
    """Build a ComfyUIClient whose module httpx binding uses MockTransport(handler)."""

    def _build(handler: Callable, base_url: str = BASE) -> tuple[ComfyUIClient, httpx.MockTransport]:
        transport = httpx.MockTransport(handler)

        def _async_client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return httpx.AsyncClient(*args, **kwargs)

        shim = SimpleNamespace(
            AsyncClient=_async_client_factory,
            HTTPStatusError=httpx.HTTPStatusError,
            TransportError=httpx.TransportError,
        )
        monkeypatch.setattr(client_module, "httpx", shim)
        return ComfyUIClient(base_url=base_url), transport

    return _build


# --- health_check -------------------------------------------------------------

def test_health_check_ok(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system_stats"
        return httpx.Response(200, json={"system": {"comfyui_version": "0.2.1"}})

    client, _ = comfy(handler)
    ok, latency = asyncio.run(client.health_check())
    assert ok is True
    assert latency is not None and latency >= 0


def test_health_check_non_200(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client, _ = comfy(handler)
    ok, latency = asyncio.run(client.health_check())
    assert ok is False


def test_health_check_transport_error(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client, _ = comfy(handler)
    ok, latency = asyncio.run(client.health_check())
    assert ok is False
    assert latency is None


# --- queue_prompt --------------------------------------------------------------

def test_queue_prompt_returns_prompt_id(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/prompt"
        return httpx.Response(200, json={"prompt_id": "prompt_abc"})

    client, _ = comfy(handler)
    assert asyncio.run(client.queue_prompt({"3": {}})) == "prompt_abc"


def test_queue_prompt_http_error_raises_comfyui_error(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"node_errors": {"x": "bad"}})

    client, _ = comfy(handler)
    with pytest.raises(ComfyUIError):
        asyncio.run(client.queue_prompt({"3": {}}))


def test_queue_prompt_transport_error_raises_provider_unavailable(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("unreachable")

    client, _ = comfy(handler)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(client.queue_prompt({"3": {}}))


# --- get_history / get_outputs -------------------------------------------------

def test_get_history_returns_entry(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/history/prompt_abc"
        return httpx.Response(
            200,
            json={
                "prompt_abc": {
                    "outputs": {"14": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}
                }
            },
        )

    client, _ = comfy(handler)
    history = asyncio.run(client.get_history("prompt_abc"))
    assert history is not None
    assert history["outputs"]["14"]["images"][0]["filename"] == "a.png"


def test_get_history_missing_returns_none(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client, _ = comfy(handler)
    assert asyncio.run(client.get_history("nope")) is None


def test_get_history_transport_error_returns_none(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TransportError("down")

    client, _ = comfy(handler)
    assert asyncio.run(client.get_history("x")) is None


def test_get_outputs_filters_output_images(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "pid": {
                    "outputs": {
                        "14": {"images": [
                            {"filename": "out.png", "subfolder": "", "type": "output"},
                            {"filename": "tmp.png", "subfolder": "", "type": "temp"},
                        ]},
                        "9": {"images": []},
                    }
                }
            },
        )

    client, _ = comfy(handler)
    outputs = asyncio.run(client.get_outputs("pid"))
    assert len(outputs) == 1
    assert outputs[0]["filename"] == "out.png"


# --- download_output -----------------------------------------------------------

def test_download_output_writes_file(comfy, tmp_path) -> None:
    blob = b"\x89PNG\r\n\x1a\n fake image"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/view"
        assert request.url.params["filename"] == "out.png"
        assert request.url.params["type"] == "output"
        return httpx.Response(200, content=blob)

    client, _ = comfy(handler)
    dest = str(tmp_path / "out.png")
    ret = asyncio.run(
        client.download_output({"filename": "out.png", "subfolder": "", "type": "output"}, dest)
    )
    assert ret == dest
    assert tmp_path.joinpath("out.png").read_bytes() == blob


def test_download_output_transport_error(comfy, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("download fail")

    client, _ = comfy(handler)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(client.download_output({"filename": "out.png"}, str(tmp_path / "out.png")))


# --- upload_image --------------------------------------------------------------

def test_upload_image(comfy, tmp_path) -> None:
    src = tmp_path / "ref.png"
    src.write_bytes(b"refdata")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/upload/image"
        return httpx.Response(200, json={"name": "ref.png", "subfolder": "", "type": "input"})

    client, _ = comfy(handler)
    result = asyncio.run(client.upload_image(str(src), subfolder="refs"))
    assert result["name"] == "ref.png"


def test_upload_image_transport_error(comfy, tmp_path) -> None:
    src = tmp_path / "ref.png"
    src.write_bytes(b"refdata")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("upload fail")

    client, _ = comfy(handler)
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(client.upload_image(str(src)))


# --- cancel (best-effort, never raises) ---------------------------------------

def test_cancel_best_effort(comfy) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    client, _ = comfy(handler)
    asyncio.run(client.cancel("prompt_abc"))
    paths = [p for _, p in seen]
    assert "/interrupt" in paths
    assert "/queue" in paths


def test_cancel_failure_is_suppressed(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client, _ = comfy(handler)
    asyncio.run(client.cancel("prompt_abc"))  # must not raise


# --- get_models (P-LocalModels: /object_info checkpoint listing) ----------------

def test_get_models_parses_object_info(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/object_info/CheckpointLoaderSimple"
        return httpx.Response(
            200,
            json={
                "CheckpointLoaderSimple": {
                    "input": {
                        "required": {
                            "ckpt_name": [["a.safetensors", "b.safetensors"], {"placeholder": "false"}]
                        }
                    }
                }
            },
        )

    client, _ = comfy(handler)
    reachable, models = asyncio.run(client.get_models())
    assert reachable is True
    assert models == ["a.safetensors", "b.safetensors"]


def test_get_models_flat_list_shape(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["x.ckpt"], {}]}}}},
        )

    client, _ = comfy(handler)
    _, models = asyncio.run(client.get_models())
    assert models == ["x.ckpt"]


def test_get_models_unreachable(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client, _ = comfy(handler)
    reachable, models = asyncio.run(client.get_models())
    assert reachable is False
    assert models == []


def test_get_models_non_200(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client, _ = comfy(handler)
    reachable, models = asyncio.run(client.get_models())
    assert reachable is True
    assert models == []


def test_get_models_unexpected_shape(comfy) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client, _ = comfy(handler)
    reachable, models = asyncio.run(client.get_models())
    assert reachable is True
    assert models == []
