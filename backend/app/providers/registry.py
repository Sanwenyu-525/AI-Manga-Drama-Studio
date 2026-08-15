"""ProviderRegistry (backend-architecture §17, §37; mvp-spec §65).

Selects the image provider by canonical provider id: "mock" | "comfyui".
P1-E2-T01: the persisted generation.provider IS the executed implementation —
get_image_provider(provider_id) resolves the id the worker must use, and an
unknown id raises ValidationError (422) instead of silently falling back.
Future: video/vision/audio registries + provider capabilities (contract §130-131).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.providers.image.base import ImageProvider
from app.providers.image.comfyui import ComfyUIProvider
from app.providers.image.mock import MockImageProvider

logger = get_logger("providers.registry")

IMAGE_PROVIDERS = ("mock", "comfyui")

_image_providers: dict[str, ImageProvider] = {}
_comfyui_provider: ComfyUIProvider | None = None


def get_image_provider(provider_id: str | None = None) -> ImageProvider:
    """Resolve a canonical provider id → the implementation that will actually run.

    provider_id=None → studio default (settings.image_provider). Unknown ids raise
    ValidationError — callers (GenerationService) surface it as a 422 before queuing.
    """
    pid = provider_id or settings.image_provider
    if pid not in IMAGE_PROVIDERS:
        raise ValidationError(
            "Unknown image provider.",
            {"provider": pid, "supported": list(IMAGE_PROVIDERS)},
        )
    cached = _image_providers.get(pid)
    if cached is not None:
        return cached
    if pid == "comfyui":
        provider: ImageProvider = get_comfyui_provider()
        logger.info("image provider: comfyui (%s)", settings.comfyui_url)
    else:
        provider = MockImageProvider()
        logger.info("image provider: mock (STUDIO_IMAGE_PROVIDER=mock; set comfyui for real generation)")
    _image_providers[pid] = provider
    return provider


def get_comfyui_provider() -> ComfyUIProvider:
    global _comfyui_provider
    if _comfyui_provider is None:
        _comfyui_provider = ComfyUIProvider()
    return _comfyui_provider


def provider_status() -> list[dict]:
    """Provider status DTO (contract §47)."""
    comfyui = get_comfyui_provider()
    providers = [
        {
            "id": "mock",
            "name": "Mock Image Provider",
            "type": "image",
            "status": "connected",
            "capabilities": {"image_generation": True, "reference_image": False},
        },
        {
            "id": "comfyui_local",
            "name": "Local ComfyUI",
            "type": "image",
            "status": "unknown",
            "capabilities": {"image_generation": True, "reference_image": True},
            "base_url": settings.comfyui_url,
        },
    ]
    if settings.image_provider == "comfyui":
        providers[1]["status"] = "active"
    return providers


def reset_providers() -> None:
    """Reset cached providers (used by tests)."""
    global _comfyui_provider
    _image_providers.clear()
    _comfyui_provider = None
