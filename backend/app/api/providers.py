"""Provider API (api-event-contract §47-48): status + ComfyUI connection test."""

from fastapi import APIRouter

from app.providers.registry import get_comfyui_provider, provider_status

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
def list_providers() -> list[dict]:
    return provider_status()


@router.post("/comfyui/test")
async def test_comfyui() -> dict:
    connected, latency = await get_comfyui_provider().health_check()
    return {"connected": connected, "latency_ms": latency}
