"""Provider API (api-event-contract §47-48): status + ComfyUI connection test."""

from fastapi import APIRouter

from app.providers.registry import get_comfyui_provider, provider_status

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
def list_providers() -> list[dict]:
    return provider_status()


@router.post("/comfyui/test")
async def test_comfyui() -> dict:
    """Health + template preflight (P1-E2-T01): a correctly configured ComfyUI must
    also pass the default workflow preflight before we call it production-ready."""
    from app.core.errors import ComfyUIError
    from app.providers.comfyui.workflow_mapper import (
        DEFAULT_WORKFLOW_ID,
        WorkflowMapper,
    )

    connected, latency = await get_comfyui_provider().health_check()
    result: dict = {"connected": connected, "latency_ms": latency}
    if connected:
        mapper = WorkflowMapper()
        try:
            mapper.preflight()
            result["workflow"] = {"id": DEFAULT_WORKFLOW_ID, "status": "ok", "output_node": mapper.output_node_id}
        except ComfyUIError as exc:
            result["workflow"] = {"id": DEFAULT_WORKFLOW_ID, "status": "error", "error": exc.message}
    return result
