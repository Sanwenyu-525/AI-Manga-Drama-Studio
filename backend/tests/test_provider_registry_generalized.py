"""P4-T001 + P4-T002: generalized ProviderRegistry + adapter family.

Covers:
- multi-type resolution (image / video / workflow / llm) by canonical id.
- unknown id -> ValidationError (422) for every type (kept semantics).
- video mock provider is registered but *unavailable* — calling it fails clearly.
- provider_status() exposes complete capabilities per provider (contract §47 / §130).
- get_image_provider() stays backward compatible (existing callers untouched).
- MVP video rejection: create_generation(type=video) -> 422 fail-fast.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ProviderUnavailableError, ValidationError
from app.providers import registry
from app.providers.registry import (
    IMAGE_PROVIDERS,
    LLM_PROVIDERS,
    VIDEO_PROVIDERS,
    WORKFLOW_PROVIDERS,
)


def test_registry_resolves_each_type() -> None:
    registry.reset_providers()
    try:
        assert registry.get_image_provider("mock") is not None
        assert registry.get_image_provider("comfyui").name == "comfyui"
        assert registry.get_video_provider("mock").name == "mock"
        assert registry.get_workflow_provider("comfyui").name == "comfyui"
        assert registry.get_llm_provider("fake") is not None
    finally:
        registry.reset_providers()


def test_each_type_rejects_unknown_id_422() -> None:
    registry.reset_providers()
    try:
        with pytest.raises(ValidationError):
            registry.get_video_provider("bogus_video")
        with pytest.raises(ValidationError):
            registry.get_workflow_provider("bogus_workflow")
        with pytest.raises(ValidationError):
            registry.get_llm_provider("bogus_llm")
        with pytest.raises(ValidationError):
            registry.get_image_provider("bogus_image")
    finally:
        registry.reset_providers()


def test_video_provider_registered_but_unavailable() -> None:
    """The mock video provider is REGISTERED (so future engines slot in), but any real
    call fails fast — MVP never silently pretends video works."""
    registry.reset_providers()
    try:
        provider = registry.get_video_provider("mock")
        assert provider is not None
        from app.providers.video.base import VideoRequest

        async def _call() -> None:
            await provider.generate(VideoRequest(prompt="nope"), lambda p, s: None)

        with pytest.raises(ProviderUnavailableError) as excinfo:
            asyncio.run(_call())
        assert excinfo.value.status_code == 503
        assert "image" in str(excinfo.value.message)
    finally:
        registry.reset_providers()


def test_video_provider_cancel_rejects() -> None:
    registry.reset_providers()
    try:
        provider = registry.get_video_provider("mock")
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(provider.cancel("x"))
    finally:
        registry.reset_providers()


def test_provider_status_has_complete_capabilities() -> None:
    status = registry.provider_status()
    types = {item["type"] for item in status}
    assert {"image", "video", "workflow", "llm"} <= types

    image = next(item for item in status if item["type"] == "image" and item["id"] == "mock")
    assert image["capabilities"]["image_generation"] is True
    assert "reference_image" in image["capabilities"]

    video = next(item for item in status if item["type"] == "video")
    assert "video_generation" in video["capabilities"]
    assert video["status"] == "unavailable"

    llm_status = next(item for item in status if item["type"] == "llm")
    assert llm_status["capabilities"]["text_generation"] is True


def test_provider_status_image_fields_backward_compatible() -> None:
    """Legacy image entries keep id/name/type/status/capabilities/base_url."""
    status = registry.provider_status()
    by_id = {item["id"]: item for item in status}
    mock = by_id["mock"]  # image mock (the only "mock" id left)
    assert mock["type"] == "image"
    assert "status" in mock and "capabilities" in mock
    comfy = by_id["comfyui_local"]
    assert comfy["type"] == "image"
    assert "base_url" in comfy
    assert "capabilities" in comfy


def test_canonical_provider_sets() -> None:
    assert "mock" in IMAGE_PROVIDERS and "comfyui" in IMAGE_PROVIDERS
    assert VIDEO_PROVIDERS == ("mock",)
    assert WORKFLOW_PROVIDERS == ("comfyui",)
    assert "fake" in LLM_PROVIDERS and "openai" in LLM_PROVIDERS


def test_workflow_adapter_builds_and_preflights() -> None:
    """Business code obtains workflows only via the adapter, never the template dir."""
    from app.providers.workflow.base import WorkflowBuildInput

    adapter = registry.get_workflow_provider("comfyui")
    result = adapter.preflight()
    assert result.ok is True
    assert result.output_node_id is not None

    built = adapter.build(WorkflowBuildInput(prompt="hello", seed=1, width=64, height=64))
    assert isinstance(built, dict)
    assert "SaveImage" in {node["class_type"] for node in built.values()}


def test_llm_adapter_resolves_fake() -> None:
    registry.reset_providers()
    try:
        gateway = registry.get_llm_provider("fake")
        text = asyncio.run(gateway.invoke("system", "hello"))
        assert isinstance(text, str)
    finally:
        registry.reset_providers()


# ------------------------ MVP video rejection ----------------------------

def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P4Registry"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, night"},
    ).json()


def test_create_generation_video_rejected_422(client: TestClient) -> None:
    """MVP rejects video at the service boundary with a fail-fast 422 (contract §41)."""
    shot = _make_shot(client)
    resp = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "video"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["type"] == "video"
    assert err["details"]["supported"] == ["image"]


def test_image_generation_still_works_via_registry(client: TestClient) -> None:
    """Regression: the generalized registry still drives the image chain end to end."""
    from app.generations.worker import run_generation

    shot = _make_shot(client)
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    assert created["status"] == "queued"
    asyncio.run(run_generation(created["id"]))
    done = client.get(f"/api/v1/generations/{created['id']}").json()
    assert done["status"] == "completed", done.get("error_message")
