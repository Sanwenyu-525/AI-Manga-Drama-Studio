"""Provider API (api-event-contract §47-48): status + ComfyUI/Agnes connection tests.

GET /providers extends the legacy provider_status() fields (id/name/type/status/
capabilities/base_url) with a backward-compatible health block (available /
unavailable / degraded, last_checked_at, latency_ms) from ProviderHealthService.
POST /comfyui/test probes ComfyUI (optional unsaved base_url override) and refreshes
the health cache (P4-T003). GET /comfyui/models lists checkpoints via /object_info.
POST /agnes/test probes the Agnes image gateway via GET /models (never raises,
never consumes image quota).
POST /models/scan scans a user path (or well-known default locations) for local
model files; POST /models/import queues the file import as a 202 Operation.
GET /fs/list is the read-only directory listing behind the settings-page path
browser (empty path → root/drives listing).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

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


class ComfyUITestRequest(BaseModel):
    """Optional override so an unsaved base_url can be probed first (mirrors /llm/test)."""

    base_url: str | None = None


@router.post("/comfyui/test")
async def test_comfyui(body: ComfyUITestRequest | None = None) -> dict:
    """Health + template preflight (P1-E2-T01 / P4-T003): probes ComfyUI, refreshes the
    health cache, and reports the default workflow preflight status. An unsaved
    base_url override is probed directly without touching the cached provider."""
    from app.core.errors import ComfyUIError
    from app.providers.comfyui.workflow_mapper import (
        DEFAULT_WORKFLOW_ID,
        WorkflowMapper,
    )
    from app.providers.image.comfyui import ComfyUIProvider

    override = (body.base_url or "").strip() if body is not None else ""
    provider = ComfyUIProvider(base_url=override) if override else get_comfyui_provider()
    health = await get_provider_health_service().refresh_comfyui(provider)
    connected = health["status"] == "available"
    result: dict = {"connected": connected, "health": health}
    if override:
        result["base_url"] = override
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


@router.get("/comfyui/models")
async def list_comfyui_models(base_url: str | None = None) -> dict:
    """Checkpoint filenames from the ComfyUI server (never raises).

    Reads the runtime image.json comfyui_url unless an override query param is given
    (probe-before-save). {connected, base_url, models} — UI renders "not connected"
    from data instead of an error.
    """
    from app.providers.comfyui.client import ComfyUIClient
    from app.services.image_settings_service import get_image_config

    url = (base_url or "").strip() or get_image_config()["comfyui_url"]
    reachable, models = await ComfyUIClient(url).get_models()
    return {"connected": reachable, "base_url": url, "models": models}


class AgnesTestRequest(BaseModel):
    """Optional overrides so an unsaved base_url can be probed first (mirrors /llm/test)."""

    base_url: str | None = None


@router.post("/agnes/test")
async def test_agnes(body: AgnesTestRequest | None = None) -> dict:
    """Agnes connectivity probe: GET /models with the configured STUDIO_AGNES_API_KEY.

    200 + {connected: ...} shape — never raises (contract §47.4, same convention as
    POST /llm/test). Never consumes image-generation quota.
    """
    from app.providers.image.agnes import AgnesImageProvider

    override = body.base_url if body is not None else None
    return await AgnesImageProvider(base_url=override).probe()


class ModelScanRequest(BaseModel):
    """path 给定 → 扫描该目录；省略 → 自动检索本机常见默认位置。"""

    path: str | None = None


@router.post("/models/scan")
def scan_models(body: ModelScanRequest | None = None) -> dict:
    """Local model discovery: path scan (bounded DFS) or well-known-location
    autodetect. Bad paths raise ValidationError (422); discovery itself never raises."""
    from app.services.local_model_scan_service import scan_default_locations, scan_model_path

    path = (body.path or "").strip() if body is not None else ""
    if path:
        return scan_model_path(path)
    return scan_default_locations()


class ModelImportRequest(BaseModel):
    """Import a local model file into the ComfyUI models directory."""

    source: str
    kind: str = "checkpoint"
    models_root: str | None = None
    overwrite: bool = False


@router.post("/models/import", status_code=202)
async def import_model(body: ModelImportRequest) -> dict:
    """Queue a model-file import (link-or-copy, GB-scale) as a background Operation.

    202 + {operation_id} per the long-task contract (§15): GET /operations/{id}
    polls queued/running/completed/failed. Validation (source/kind/root/conflict)
    happens synchronously first so bad requests get 422/409 immediately.
    """
    from app.operations.store import operation_store
    from app.services.local_model_scan_service import execute_import, resolve_import_target

    src, target = resolve_import_target(
        body.source, body.kind, body.models_root, overwrite=body.overwrite
    )
    op = operation_store.create("model_import")
    operation_store.start(
        op["id"],
        lambda: asyncio.to_thread(execute_import, src, target, overwrite=body.overwrite),
    )
    return {"operation_id": op["id"], "status": op["status"]}


@router.get("/fs/list")
def list_fs_directory(path: str | None = None) -> dict:
    """Read-only directory listing for the settings-page path browser (§48.6).

    No path → root listing (Windows drives / POSIX /). Bad path → 422;
    unreadable dirs degrade to entries=[] + error note (never 500).
    """
    from app.services.filesystem_service import list_directory

    return list_directory(path)
