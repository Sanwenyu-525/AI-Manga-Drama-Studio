"""VideoProviderProtocol — the adapter Protocol the business layer composes against
(backend-architecture §39). We name it *Protocol* so it will not clash with a future
concrete ComfyUI VideoProvider implementation.

MVP: video generation is rejected at the API/service boundary with a fail-fast
422 (contract §41). The protocol + Studio Domain Contract Request/Result still exist
so Phase 4's "business layer knows no model" holds for video before any engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class VideoRequest:
    """Normalized Studio-side video request — provider-agnostic (contract §7)."""

    prompt: str
    negative_prompt: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None  # seconds
    fps: int | None = None
    reference_images: list[str] = field(default_factory=list)  # absolute paths
    workflow_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    """Normalized video result — provider-agnostic."""

    success: bool
    output_path: str | None = None  # absolute path to generated video file
    provider_ref: str | None = None
    duration: float | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


class VideoProviderProtocol(Protocol):
    """Async video generation interface (backend-architecture §39)."""

    name: str

    async def generate(self, request: VideoRequest, on_progress) -> VideoResult:
        """Generate one video clip; on_progress(percent: int, stage: str)."""
        ...

    async def cancel(self, provider_ref: str) -> None:
        """Best-effort cancel of a running video generation."""
        ...
