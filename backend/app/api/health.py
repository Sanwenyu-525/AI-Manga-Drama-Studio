"""Health endpoint (api-event-contract §140, P1-E4-T03).

Statuses: "healthy" | "degraded" | "unhealthy" (database) / "stopped"
(worker) / "unavailable" (providers). overall is "healthy" only when every
component is healthy; a dead worker, a stopped gateway, or an unusable
configured provider yields "degraded" (never silently "healthy"). A dead
database yields "unhealthy". Probes are cheap and synchronous — no network
I/O here (ComfyUI state comes from the cached ProviderHealthService).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Component-level health: database + worker + event_bus + providers."""
    from app.events.ws import gateway_status
    from app.generations.worker import WORKER_STALE_SECONDS, worker_heartbeat_age_seconds
    from app.services.provider_health_service import (
        HEALTH_AVAILABLE,
        get_provider_health_service,
    )

    database = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "unhealthy"

    age = worker_heartbeat_age_seconds()
    worker = "healthy" if age is not None and age < WORKER_STALE_SECONDS else "stopped"

    gateway = gateway_status()
    event_bus = "healthy" if gateway["started"] else "degraded"

    # Providers: report the configured image provider without probing the network.
    # mock is always available; comfyui reflects the cached probe (unknown until
    # the first POST /providers/comfyui/test or startup refresh).
    provider_service = get_provider_health_service()
    providers: dict[str, str] = {}
    providers_ok = True
    image_provider = settings.image_provider
    if image_provider == "comfyui":
        cached = provider_service.get_comfyui_health()
        connected = cached.get("status") == HEALTH_AVAILABLE
        providers["comfyui"] = "connected" if connected else "unavailable"
        if not connected:
            providers_ok = False
    else:
        # mock / agnes: no cheap probe; mock is always available, agnes key
        # presence is validated at generation time, not here.
        providers[image_provider] = "available"
    if settings.app_env == "production" and image_provider == "mock":
        # Defense in depth alongside validate_startup_config (which refuses to
        # boot this combination): a production process that somehow runs with a
        # fake-content provider must not report healthy.
        providers_ok = False

    if database == "unhealthy":
        overall = "unhealthy"
    elif worker == "healthy" and event_bus == "healthy" and providers_ok:
        overall = "healthy"
    else:
        overall = "degraded"
    return {
        "status": overall,
        "database": database,
        "worker": worker,
        "event_bus": event_bus,
        "providers": providers,
        "backend_version": "0.1.0",
        "api_version": "1",
        "event_protocol_version": "1",
        "env": settings.app_env,
    }


@router.get("/system/info")
def system_info() -> dict:
    return {
        "backend_version": "0.1.0",
        "api_version": "1",
        "event_protocol_version": "1",
    }
