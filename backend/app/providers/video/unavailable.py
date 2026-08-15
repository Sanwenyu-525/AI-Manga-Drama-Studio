"""VideoProviderUnavailable — the MVP video placeholder (P4-T002).

The mock video provider is REGISTERED in ProviderRegistry so the capability is
visible (type=video, id=mock), but it is deliberately *unavailable*: any actual
call fails fast with a clear Studio error. MVP supports image only — we never
silently pretend a video provider is usable.
"""

from __future__ import annotations

from app.core.errors import ProviderUnavailableError
from app.providers.video.base import VideoRequest, VideoResult


class VideoProviderUnavailable:
    """VideoProviderProtocol impl that always rejects — MVP has no video engine."""

    name = "mock"  # canonical video provider id placeholder

    async def generate(self, request: VideoRequest, on_progress) -> VideoResult:
        raise ProviderUnavailableError(
            "Video generation is not available in MVP; only image generation is supported.",
            {"type": "video", "provider": self.name, "supported": ["image"]},
        )

    async def cancel(self, provider_ref: str) -> None:
        raise ProviderUnavailableError(
            "Video generation is not available in MVP.",
            {"type": "video", "provider": self.name},
        )
