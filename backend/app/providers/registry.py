"""ProviderRegistry (backend-architecture §17, §37; mvp-spec §65).

Selects the image provider by STUDIO_IMAGE_PROVIDER (mock|comfyui).
Future: video/vision/audio registries + provider capabilities (contract §130-131).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.image.base import ImageProvider
from app.providers.image.comfyui import ComfyUIProvider
from app.providers.image.mock import MockImageProvider

logger = get_logger("providers.registry")

_image_provider: ImageProvider | None = None
_comfyui_provider: ComfyUIProvider | None = None


def get_image_provider() -> ImageProvider:
    global _image_provider
    if _image_provider is not None:
        return _image_provider
    if settings.image_provider == "comfyui":
        _image_provider = get_comfyui_provider()
        logger.info("image provider: comfyui (%s)", settings.comfyui_url)
    else:
        _image_provider = MockImageProvider()
        logger.info("image provider: mock (STUDIO_IMAGE_PROVIDER=mock; set comfyui for real generation)")
    return _image_provider


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
    global _image_provider, _comfyui_provider
    _image_provider = None
    _comfyui_provider = None
