"""Provider API (api-event-contract §47-48): status + ComfyUI connection test.

GET /providers extends the legacy provider_status() fields (id/name/type/status/
capabilities/base_url) with a backward-compatible health block (available /
unavailable / degraded, last_checked_at, latency_ms) from ProviderHealthService.
POST /comfyui/test probes ComfyUI and refreshes the health cache (P4-T003).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.providers.registry import get_comfyui_provider, provider_status
from app.services.provider_health_service import (
    COMFYUI_PROVIDER_ID,
    MOCK_PROVIDER_ID,
    get_provider_health_service,
)

router = APIRouter(prefix="/providers", tags=["providers"])


def _with_health(items: list[dict]) -> list[dict]:
    health = get_provider_health_service().get_all()
    for item in items:
        pid = item.get("id")
        if pid == MOCK_PROVIDER_ID:
            item["health"] = health[MOCK_PROVIDER_ID]
        elif pid == COMFYUI_PROVIDER_ID:
            item["health"] = health[COMFYUI_PROVIDER_ID]
    return items


@router.get("")
def list_providers() -> list[dict]:
    return _with_health(provider_status())


@router.post("/comfyui/test")
async def test_comfyui() -> dict:
    """Health + template preflight (P1-E2-T01 / P4-T003): probes ComfyUI, refreshes the
    health cache, and reports the default workflow preflight status."""
    from app.core.errors import ComfyUIError
    from app.providers.comfyui.workflow_mapper import (
        DEFAULT_WORKFLOW_ID,
        WorkflowMapper,
    )

    health = await get_provider_health_service().refresh_comfyui(get_comfyui_provider())
    connected = health["status"] == "available"
    result: dict = {"connected": connected, "health": health}
    if health["latency_ms"] is not None:
        result["latency_ms"] = health["latency_ms"]
    if connected:
        mapper = WorkflowMapper()
        try:
            mapper.preflight()
            result["workflow"] = {"id": DEFAULT_WORKFLOW_ID, "status": "ok", "output_node": mapper.output_node_id}
        except ComfyUIError as exc:
            result["workflow"] = {"id": DEFAULT_WORKFLOW_ID, "status": "error", "error": exc.message}
    return result
