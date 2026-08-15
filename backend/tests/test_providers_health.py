"""P4-T003: ProviderHealthService — health block on GET /providers + test refresh."""

from fastapi.testclient import TestClient

from app.api import providers as providers_api
from app.services.provider_health_service import (
    COMFYUI_PROVIDER_ID,
    HEALTH_AVAILABLE,
    MOCK_PROVIDER_ID,
    get_provider_health_service,
)


# --- unit: mock always available ---

def test_mock_provider_always_available() -> None:
    service = get_provider_health_service()
    health = service.get_mock_health()
    assert health["status"] == HEALTH_AVAILABLE
    assert health["last_checked_at"] is not None
    assert health["latency_ms"] is None


def test_comfyui_unavailable_until_probed() -> None:
    get_provider_health_service().reset()
    health = get_provider_health_service().get_comfyui_health()
    assert health["status"] == "unavailable"
    assert health["last_checked_at"] is None


# --- GET /providers carries a backward-compatible health block ---

def test_providers_endpoint_has_health_block(client: TestClient) -> None:
    resp = client.get("/api/v1/providers")
    assert resp.status_code == 200
    items = resp.json()
    by_id = {item["id"]: item for item in items}
    assert MOCK_PROVIDER_ID in by_id
    assert COMFYUI_PROVIDER_ID in by_id

    mock = by_id[MOCK_PROVIDER_ID]
    assert mock["health"]["status"] == HEALTH_AVAILABLE
    assert "last_checked_at" in mock["health"]
    # old status field preserved
    assert mock["status"] == "connected"
    assert "capabilities" in mock

    comfy = by_id[COMFYUI_PROVIDER_ID]
    assert "health" in comfy
    assert "status" in comfy  # legacy field kept
    assert "base_url" in comfy


# --- POST /comfyui/test refreshes the health cache ---

def test_comfyui_test_refreshes_health_cache(client: TestClient, monkeypatch) -> None:
    get_provider_health_service().reset()

    class _FakeComfy:
        async def health_check(self):
            return True, 12.0

    monkeypatch.setattr(providers_api, "get_comfyui_provider", lambda: _FakeComfy())
    resp = client.post("/api/v1/providers/comfyui/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["health"]["status"] == HEALTH_AVAILABLE
    assert body["health"]["latency_ms"] == 12.0
    assert body["health"]["last_checked_at"] is not None
    assert body["latency_ms"] == 12.0

    # GET /providers now reads the refreshed cache
    items = client.get("/api/v1/providers").json()
    comfy = next(item for item in items if item["id"] == COMFYUI_PROVIDER_ID)
    assert comfy["health"]["status"] == HEALTH_AVAILABLE
    assert comfy["health"]["latency_ms"] == 12.0


def test_comfyui_test_unavailable_status(client: TestClient, monkeypatch) -> None:
    get_provider_health_service().reset()

    class _FakeComfyDown:
        async def health_check(self):
            return False, None

    monkeypatch.setattr(providers_api, "get_comfyui_provider", lambda: _FakeComfyDown())
    body = client.post("/api/v1/providers/comfyui/test").json()
    assert body["connected"] is False
    assert body["health"]["status"] == "unavailable"
    assert "workflow" not in body
