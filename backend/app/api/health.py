"""Health endpoint (api-event-contract §140)."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Component-level health (P1-E4-T03 extends this; P1-E2-T02 adds the worker)."""
    from app.generations.worker import WORKER_STALE_SECONDS, worker_heartbeat_age_seconds

    database = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "unhealthy"

    age = worker_heartbeat_age_seconds()
    worker = "healthy" if age is not None and age < WORKER_STALE_SECONDS else "stopped"

    overall = "healthy" if database == "healthy" and worker == "healthy" else "degraded"
    return {
        "status": overall,
        "database": database,
        "worker": worker,
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
