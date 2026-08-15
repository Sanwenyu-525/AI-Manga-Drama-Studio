"""ProviderHealthService (P4-T003) — in-memory provider health state.

Tracks available / unavailable / degraded with last_checked_at + latency_ms per
canonical provider id. MockImageProvider is always available; the ComfyUI provider is
probed through its existing health_check(); POST /providers/comfyui/test reuses and
refreshes this cache. GET /api/v1/providers reads the cached state (backward compatible).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger("providers.health")

HEALTH_AVAILABLE = "available"
HEALTH_UNAVAILABLE = "unavailable"
HEALTH_DEGRADED = "degraded"

MOCK_PROVIDER_ID = "mock"
COMFYUI_PROVIDER_ID = "comfyui_local"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProviderHealthService:
    """Maintains the health cache. Sync reads + async refresh (ComfyUI probe)."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def _entry(self, provider_id: str) -> dict[str, Any]:
        return self._cache.setdefault(
            provider_id,
            {"status": HEALTH_UNAVAILABLE, "last_checked_at": None, "latency_ms": None},
        )

    # --- sync state (GET /providers) ---

    def get_mock_health(self) -> dict[str, Any]:
        """MockImageProvider is always available."""
        entry = self._entry(MOCK_PROVIDER_ID)
        entry["status"] = HEALTH_AVAILABLE
        if entry["last_checked_at"] is None:
            entry["last_checked_at"] = _now()
        return dict(entry)

    def get_comfyui_health(self) -> dict[str, Any]:
        """Cached ComfyUI probe state (None until a probe runs)."""
        return dict(self._entry(COMFYUI_PROVIDER_ID))

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Current health for every known provider (initiates mock's cache)."""
        return {
            MOCK_PROVIDER_ID: self.get_mock_health(),
            COMFYUI_PROVIDER_ID: self.get_comfyui_health(),
        }

    def reset(self) -> None:
        self._cache.clear()

    # --- async refresh (POST /providers/comfyui/test + startup) ---

    async def refresh_comfyui(self, provider=None) -> dict[str, Any]:
        """Probe ComfyUI and cache the result. Returns the updated health block."""
        from app.providers.registry import get_comfyui_provider

        probe = provider if provider is not None else get_comfyui_provider()
        entry = self._entry(COMFYUI_PROVIDER_ID)
        try:
            connected, latency = await probe.health_check()
            entry["connected"] = bool(connected)
            entry["status"] = HEALTH_AVAILABLE if connected else HEALTH_UNAVAILABLE
            entry["latency_ms"] = latency
        except Exception as exc:  # noqa: BLE001 — probe must never raise to the caller
            logger.warning("comfyui health probe failed: %s", exc)
            entry["connected"] = False
            entry["status"] = HEALTH_UNAVAILABLE
            entry["latency_ms"] = None
        entry["last_checked_at"] = _now()
        logger.info("comfyui health refreshed: status=%s latency_ms=%s", entry["status"], entry["latency_ms"])
        return dict(entry)

    # --- degraded helper (reserved; not used by MVP providers) ---

    @staticmethod
    def mark_degraded(entry: dict[str, Any], reason: str) -> dict[str, Any]:
        entry["status"] = HEALTH_DEGRADED
        entry["reason"] = reason
        entry["last_checked_at"] = _now()
        return entry


# Module-level singleton cache so GET reads persist the refreshed probe result.
_health_service = ProviderHealthService()


def get_provider_health_service() -> ProviderHealthService:
    return _health_service


def reset_provider_health() -> None:
    _health_service.reset()
