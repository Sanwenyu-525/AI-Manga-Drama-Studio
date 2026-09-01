"""Asset DTOs (P3-T003/T005, P6-B): asset read/missing-check summary + browser read models."""

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


class AssetListItemRead(BaseModel):
    """Asset Browser list item (P6-B): summary row of a project-scope asset list.

    file_path is the portable project-relative path; thumbnail_url routes through
    the existing /assets/{id}/thumbnail endpoint. width/height resolve from the
    asset columns, falling back to meta_json when the columns are unset.
    """

    id: str
    type: str
    status: str
    # name/source_type back the browser's grouping (storyboard/character/location
    # tabs) and MASTER badges — the frontend list row consumes both (P6-B contract).
    name: str | None = None
    source_type: str = "generated"
    version_group_id: str | None = None
    version_number: int | None = None
    checksum: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    created_at: str
    file_path: str | None = None  # relative to the portable project dir
    thumbnail_url: str | None = None


class AssetListRead(BaseModel):
    """Paginated project-scope asset list (P6-B): {total, items[...]}."""

    total: int
    items: list[AssetListItemRead]


class AssetDetailRead(BaseModel):
    """Single-asset full detail (P6-B Inspector): list fields + provenance refs.

    Adds meta_json and the generation_id / parent_asset_id chain, plus a
    shot_id reference summary parsed from version_group_id (vg:shot:{id}:{PURPOSE}).
    """

    id: str
    project_id: str
    type: str
    status: str
    version_group_id: str | None = None
    version_number: int | None = None
    checksum: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    created_at: str
    file_path: str | None = None  # relative to the portable project dir
    thumbnail_url: str | None = None
    meta_json: str | None = None
    generation_id: str | None = None
    parent_asset_id: str | None = None
    shot_id: str | None = None  # reference summary via version_group_id


class AssetMissingCheckRead(BaseModel):
    """Summary of a missing-asset scan (P3-T005):

    checked = number of ready assets inspected (files that should exist);
    missing = number transitioned ready → missing (file absent).
    Already-missing rows are skipped (not re-counted).
    """

    checked: int
    missing: int
