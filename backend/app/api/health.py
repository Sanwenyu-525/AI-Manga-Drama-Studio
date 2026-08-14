"""Health endpoint (api-event-contract §140)."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    database = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database = "unhealthy"
    return {
        "status": "healthy" if database == "healthy" else "degraded",
        "database": database,
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
