"""ImageProvider protocol (backend-architecture §38).

Business code (GenerationService) only ever sees this interface — never a concrete
provider (red line: ShotService/GenerationService must not know specific models).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ImageRequest:
    """Normalized Studio-side request — provider-agnostic (contract §7)."""

    prompt: str
    negative_prompt: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    reference_images: list[str] = field(default_factory=list)  # absolute paths
    workflow_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ImageResult:
    """Normalized result — provider-agnostic."""

    success: bool
    output_path: str | None = None  # absolute path to generated image file
    provider_ref: str | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


class ImageProvider(Protocol):
    """Async image generation interface (backend-architecture §38)."""

    name: str

    async def generate(self, request: ImageRequest, on_progress) -> ImageResult:
        """Generate one image; on_progress(percent: int, stage: str) called during the run."""
        ...

    async def cancel(self, provider_ref: str) -> None:
        """Best-effort cancel of a running generation."""
        ...
