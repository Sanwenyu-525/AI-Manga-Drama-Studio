"""RenderProviderProtocol (Phase 9, P9-E3) — assembles a timeline into a video.

The business layer only speaks this Studio domain contract (red line §7): a
RenderRequest of normalized clips → a RenderResult with the final file + stats.
Concrete engines (mock / ffmpeg) live behind the registry; the worker never sees
encoder specifics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RenderClip:
    """One timeline clip resolved to a real source file for the renderer."""

    source_path: str  # absolute path to the bound asset file
    kind: str  # "image" | "video" | "audio" | "subtitle"
    start: float  # timeline start (seconds)
    end: float  # timeline end (seconds)
    source_in: float = 0.0  # offset into the source media
    source_out: float | None = None
    text: str | None = None  # subtitle text (SUBTITLE clips); narration copy (metadata)
    transition: str = "cut"  # P4-E3-T02 (AC-2): cut | fade | dissolve at the clip head


@dataclass
class RenderRequest:
    output_path: str  # absolute path the encoder writes
    width: int = 720
    height: int = 1280
    fps: float = 24.0
    clips: list[RenderClip] = field(default_factory=list)
    # TASK-013: VOICE/MUSIC/SFX clips (kind="audio", real files) mixed under the
    # video track, and SUBTITLE clips burned in / drawn onto frames.
    audio_clips: list[RenderClip] = field(default_factory=list)
    subtitle_clips: list[RenderClip] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class RenderResult:
    success: bool
    output_path: str | None = None
    duration: float | None = None
    frame_count: int | None = None
    error: str | None = None
    extra: dict = field(default_factory=dict)


class RenderProviderProtocol(Protocol):
    name: str
    # File extension the encoder writes (e.g. ".mp4" / ".avi"). Declared by the
    # provider so the worker never branches on concrete engine names.
    output_extension: str

    async def render(self, request: RenderRequest, on_progress) -> RenderResult:
        """Render the clips into output_path; on_progress(percent, stage)."""
        ...

    async def cancel(self, provider_ref: str) -> None:
        """Best-effort cancel of a running render."""
        ...
