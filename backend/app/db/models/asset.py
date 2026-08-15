"""Asset model (database-v0.1 §13, mvp-spec §19; ADR-001): every real file registered here.

ADR-001 (asset self-versioning): assets carry their own version semantics —
version_group_id (vg:{owner_type}:{owner_id}:{purpose}) + version_number,
status, source_type, checksum. Active selection lives on the owner
(shots.active_*_asset_id); media_versions was merged into this table.
"""

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, uuid_pk

ASSET_TYPES = ("image", "video", "audio", "reference", "document", "workflow", "thumbnail", "other")

ASSET_STATUSES = ("ready", "processing", "stale", "missing", "corrupted", "failed", "archived")
ASSET_SOURCE_TYPES = ("generated", "imported", "edited", "derived", "captured")


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        # ADR-001: one version number per group among live rows
        Index(
            "uq_assets_version",
            "version_group_id",
            "version_number",
            unique=True,
            sqlite_where=text("version_group_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("idx_assets_version_group", "version_group_id"),
        Index("idx_assets_generation", "generation_id"),
        Index("idx_assets_parent", "parent_asset_id"),
    )

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)  # image|video|audio|reference|...
    name: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)  # relative to project dir (database-v0.1 §39)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column()
    file_size: Mapped[int | None] = mapped_column(Integer)
    meta_json: Mapped[str | None] = mapped_column(Text)  # JSON (database-v0.1 §13 "metadata")

    # ADR-001: self-versioning
    version_group_id: Mapped[str | None] = mapped_column(Text)  # vg:shot:{shot_id}:{PURPOSE}
    version_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ready")
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="generated")
    checksum: Mapped[str | None] = mapped_column(Text)  # SHA-256

    generation_id: Mapped[str | None] = mapped_column(Text)  # provenance (ADR-001 rename)
    parent_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))

    deleted_at: Mapped[str | None] = mapped_column(Text)  # soft delete
    created_at: Mapped[str] = ts_created()
