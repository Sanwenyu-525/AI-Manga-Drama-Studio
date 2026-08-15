"""Location + LocationVersion models (database-v0.1 §6, domain-model-design §35/§36; P2-T009).

Location groups reusable shot backgrounds (体育馆 / 卧室 / 天台 ...) that multiple
Scenes reference via scenes.location_id (a weak Text ref — no hard FK on Scene,
validation happens in the service layer to keep SQLite migrations minimal).

LocationVersion mirrors the CharacterVersion pattern (P2-T007/T008):
- immutable chain: edits create vN+1; soft-deleted rows excluded from numbering.
- a new version defaults to status=stale — activated only by activate_version().
- locations.master_version_id is the authoritative MASTER pointer (ADR-002 pattern);
  activation flips old active -> stale, new -> active, master -> new (single txn).
"""

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

LOCATION_STATUSES = ("active", "archived")
LOCATION_VERSION_STATUSES = ("active", "stale", "archived")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    visual_prompt: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")

    # P2-T009: authoritative MASTER pointer (ADR-002 pattern) — nullable until a
    # version is activated. Scenes bind the master look; existing scenes not updated.
    master_version_id: Mapped[str | None] = mapped_column(ForeignKey("location_versions.id"))

    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency (§88)
    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class LocationVersion(Base):
    """Location visual version (P2-T009): a versioned representative reference Asset.

    Immutable chain: edits create vN+1. Group-scoped version_number (max+1), unique
    index backstop, soft-deleted rows excluded from version_number computation.
    status: active (current MASTER) | stale (superseded) | archived.
    """

    __tablename__ = "location_versions"
    __table_args__ = (
        Index("uq_location_versions_number", "location_id", "version_number", unique=True),
        Index("ix_location_versions_asset_id", "asset_id"),
    )

    id: Mapped[str] = uuid_pk()
    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)  # representative visual
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="stale")  # active|stale|archived
    checksum: Mapped[str | None] = mapped_column(Text)

    deleted_at: Mapped[str | None] = mapped_column(Text)  # soft delete (draft versions)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
