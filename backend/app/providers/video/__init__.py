"""VideoProvider adapter family (P4-T001).

The Studio business layer depends on VideoProviderProtocol (and the
VideoRequest / VideoResult Studio Domain Contracts) — never on a concrete
video engine. MVP rejects video generation with a fail-fast 422 (see
generation_service.create_generation), but the adapter protocol and its
registry registration must exist so Phase 4's "business layer knows no model"
holds the moment video lands.
"""

from __future__ import annotations

from app.providers.video.base import VideoProviderProtocol, VideoRequest, VideoResult
from app.providers.video.unavailable import VideoProviderUnavailable

__all__ = [
    "VideoProviderProtocol",
    "VideoRequest",
    "VideoResult",
    "VideoProviderUnavailable",
]
