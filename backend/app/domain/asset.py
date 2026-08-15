"""Asset DTOs (P3-T003/T005): imported asset read + missing-check summary."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AssetRead(BaseModel):
    """A registered asset — the ONLY way a real file is exposed (red line: no
    bare filePath returns; Router → Service → Repository)."""

    id: str
    project_id: str
    type: str
    name: str | None = None
    file_path: str | None = None  # relative to the portable project dir
    thumbnail_path: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    file_size: int | None = None
    meta: dict[str, Any] | None = None
    version_group_id: str | None = None
    version_number: int | None = None
    status: str = "ready"
    source_type: str = "generated"
    checksum: str | None = None
    generation_id: str | None = None
    parent_asset_id: str | None = None
    created_at: str


class AssetMissingCheckRead(BaseModel):
    """Summary of a missing-asset scan (P3-T005):

    checked = number of ready assets inspected (files that should exist);
    missing = number transitioned ready → missing (file absent).
    Already-missing rows are skipped (not re-counted).
    """

    checked: int
    missing: int
