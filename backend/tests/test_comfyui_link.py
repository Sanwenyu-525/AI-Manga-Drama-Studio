"""P4-T010 — real-chain ComfyUI link integration test (no real ComfyUI / WS).

Drives the full Studio closed loop against a mocked ComfyUI server (httpx.MockTransport
attached to ComfyUIClient):

    project → episode → scene → shot → POST /shots/{id}/generations
        → run_generation (worker) → ComfyUIProvider
            /system_stats → health_check
            /prompt      → prompt_id
            WS unavailable → _poll_history_fallback (monitor)
            /history/{id} → outputs from SaveImage node
            /view        → image bytes
        → Asset + version_group + generation_outputs row.

The WS path is made unavailable by stubbing websockets.connect to raise immediately, so
monitor exercises its history-polling fallback exactly as designed. The real
default_image_api.json template is used, so placeholder injection is verified end-to-end.
"""

import asyncio
import sys
import time
import types

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.generations.worker import run_generation
from app.providers import registry as provider_registry
from app.providers.comfyui import client as client_module
from app.providers.image.comfyui import ComfyUIProvider
from app.services.asset_service import project_dir

FAKE_BASE = "http://comfyui.test:8188"


def _png_bytes(width: int = 96, height: int = 128) -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 90, 200)).save(buf, "PNG")
    return buf.getvalue()


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _wait_status(client: TestClient, generation_id: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"generation {generation_id} did not finish in {timeout}s")


def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P4ComfyLink"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga, cyberpunk alley"},
    ).json()


def _make_comfyui_provider(
    png: bytes, monkeypatch, posted: list[dict]
) -> ComfyUIProvider:
    """Wire a ComfyUIProvider whose client HTTP calls go through MockTransport.

    Simulates /system_stats, /prompt, /history/{id} and /view. WS monitor is stubbed
    to raise immediately so /history polling becomes the completion source.
    """
    state = {"prompt_id": "fake-prompt-1"}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "0.2.1"}})
        if path == "/prompt":
            body = request.read()
            posted.append({"body": body, "path": path})
            return httpx.Response(200, json={"prompt_id": state["prompt_id"]})
        if path == "/history/" + state["prompt_id"]:
            return httpx.Response(
                200,
                json={
                    state["prompt_id"]: {
                        "outputs": {
                            "14": {
                                "images": [
                                    {"filename": "out.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        }
                    }
                },
            )
        if path == "/view":
            return httpx.Response(200, content=png)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def _async_client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return httpx.AsyncClient(*args, **kwargs)

    shim = types.SimpleNamespace(
        AsyncClient=_async_client_factory,
        HTTPStatusError=httpx.HTTPStatusError,
        TransportError=httpx.TransportError,
    )
    monkeypatch.setattr(client_module, "httpx", shim)

    # force WS monitor to fail fast -> history fallback. websockets.connect() is
    # expected to return an object usable in "async with"; __aenter__ raises, which
    # drops monitor into _poll_history_fallback.
    class _FailConnect:
        def __aenter__(self):
            raise OSError("ws unavailable (intentional in test)")

        async def __aexit__(self, *exc):
            return False

    fake_ws = types.SimpleNamespace(connect=lambda *a, **k: _FailConnect())
    monkeypatch.setitem(sys.modules, "websockets", fake_ws)

    provider = ComfyUIProvider()
    provider.client._base_url = FAKE_BASE  # type: ignore[attr-defined]
    return provider


def test_comfyui_link_full_chain(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "image_provider", "comfyui")
    monkeypatch.setattr(settings, "comfyui_url", FAKE_BASE)

    png = _png_bytes()
    posted: list[dict] = []
    provider = _make_comfyui_provider(png, monkeypatch, posted)
    monkeypatch.setattr(provider_registry, "get_comfyui_provider", lambda: provider)
    provider_registry.reset_providers()

    shot = _make_shot(client)

    # workflow_id omitted -> WorkflowResolver resolves the system default.
    resp = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert resp.status_code == 202
    created = resp.json()
    assert created["provider"] == "comfyui"
    assert created["workflow_id"] == "default_image_api"

    _drive(created["id"])
    done = _wait_status(client, created["id"])
    assert done["status"] == "completed", done.get("error_message")
    assert done["provider"] == "comfyui"
    assert done["output_asset_id"]

    # the mocked ComfyUI /prompt was actually hit (with the injected workflow).
    assert posted, "ComfyUI /prompt was never called"

    # Asset landed on disk inside the project store, content matches, version grouped.
    prov = client.get(f"/api/v1/assets/{done['output_asset_id']}/provenance").json()
    asset_read = prov["asset"]
    assert asset_read["version_group_id"]
    assert asset_read["version_number"] == 1
    assert asset_read["status"] == "ready"
    assert asset_read["generation_id"] == done["id"]
    disk = project_dir(asset_read["project_id"]) / asset_read["file_path"]
    assert disk.is_file()
    assert disk.read_bytes() == png
    content = client.get(f"/api/v1/assets/{asset_read['id']}/content")
    assert content.status_code == 200
    assert content.content == png

    # generation_outputs row exists for the producing generation.
    outputs = client.get(f"/api/v1/generations/{done['id']}/outputs")
    assert outputs.status_code == 200
    body = outputs.json()
    assert len(body["outputs"]) == 1
    assert body["outputs"][0]["asset_id"] == done["output_asset_id"]
    assert body["outputs"][0]["type"] == "image"
    assert body["outputs"][0]["role"] == "primary"

    # the shot received an active version (V1).
    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["is_active"] is True
