"""Timeline DTOs (api-event-contract §93, Phase 9).

Timeline (per episode) + tracks (lanes) + clips (Timeline Items bound to a
specific asset version). Renders are type='render' Generations; the final
output registers as a FINAL_VIDEO asset (vg:episode:{episode_id}:FINAL_VIDEO).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# Track types (roadmap §61 / database-v0.1 §32).
TRACK_TYPES = ("VIDEO", "VOICE", "MUSIC", "SFX", "SUBTITLE")
DEFAULT_TRACK_TYPES = ("VIDEO", "VOICE", "MUSIC", "SUBTITLE")

TIMELINE_STATUSES = ("DRAFT", "READY", "RENDERED", "RENDER_FAILED")


class TimelineClipAssetRead(BaseModel):
    """Lightweight summary of the bound asset (never the raw file path)."""

    id: str
    type: str
    name: str | None = None
    status: str = "ready"
    version_group_id: str | None = None
    version_number: int | None = None
    thumbnail_url: str | None = None
    mime_type: str | None = None


class TimelineTrackRead(BaseModel):
    id: str
    timeline_id: str
    track_type: str
    name: str | None = None
    order_index: float
    locked: int = 0
    muted: int = 0
    created_at: str


class TimelineClipRead(BaseModel):
    id: str
    timeline_id: str
    track_id: str
    asset_id: str
    shot_id: str | None = None
    start_time: float
    end_time: float
    source_in: float = 0
    source_out: float | None = None
    order_index: float = 0
    text: str | None = None  # subtitle/voice content
    enabled: int = 1
    asset: TimelineClipAssetRead | None = None
    created_at: str
    updated_at: str


class TimelineRead(BaseModel):
    id: str
    project_id: str
    episode_id: str
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    status: str = "DRAFT"
    tracks: list[TimelineTrackRead] = Field(default_factory=list)
    clips: list[TimelineClipRead] = Field(default_factory=list)
    created_at: str
    updated_at: str


# ---------------- create / update ----------------

class TimelineTrackCreate(BaseModel):
    track_type: str = "VIDEO"  # VIDEO|VOICE|MUSIC|SFX|SUBTITLE
    name: str | None = None
    order_index: float | None = None  # None → after the current max


class TimelineTrackUpdatePatch(BaseModel):
    name: str | None = None
    order_index: float | None = None
    locked: int | None = None
    muted: int | None = None


class TimelineTrackUpdateRequest(BaseModel):
    patch: TimelineTrackUpdatePatch


class TimelinePatch(BaseModel):
    """Only supplied keys are applied (exclude_unset)."""

    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    status: str | None = None


class TimelineUpdateRequest(BaseModel):
    patch: TimelinePatch


class TimelineClipCreate(BaseModel):
    track_id: str
    asset_id: str
    shot_id: str | None = None
    start_time: float = 0
    end_time: float = 3
    source_in: float = 0
    source_out: float | None = None
    order_index: float | None = None  # None → after the current max on the track
    enabled: int = 1


class TimelineClipUpdatePatch(BaseModel):
    """Drag → start_time/end_time (with same duration unless trimmed); trim → edges;
    re-track → track_id; disable → enabled."""

    track_id: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    source_in: float | None = None
    source_out: float | None = None
    order_index: float | None = None
    enabled: int | None = None


class TimelineClipUpdateRequest(BaseModel):
    patch: TimelineClipUpdatePatch


class TimelineClipReplaceRequest(BaseModel):
    """P9-T012: rebind a clip to another asset/version."""

    asset_id: str


class TimelineRenderRead(BaseModel):
    generation_id: str
    timeline_id: str
    episode_id: str | None = None
    status: str
    message: str | None = None


class FinalVideoRead(BaseModel):
    """Latest rendered episode export (FINAL_VIDEO asset) — the deliverable."""

    asset_id: str
    project_id: str
    episode_id: str
    name: str | None = None
    type: str = "video"
    version_number: int | None = None
    mime_type: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    status: str = "ready"
    content_url: str
    thumbnail_url: str | None = None
    meta: dict[str, Any] | None = None
    created_at: str