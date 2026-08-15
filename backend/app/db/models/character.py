"""Character + ShotCharacter + CharacterVersion models (database-v0.1 §7, §11; mvp-spec §105-BE; P2-T007/T008).

Character stores the *identity* (name/appearance/personality); costumes are managed
separately (costumes table comes later — default_costume_id stays a weak Text ref).
ShotCharacter is the many-to-many link table with continuity-relevant per-shot
attributes (position/pose/emotion) — MVP only fills shot_id/character_id.
CharacterVersion (P2): the character's visual versions (reference Asset per version).
characters.master_version_id is the ADR-002-style authoritative MASTER pointer to
the project-approved standard look; a new version defaults to stale and is promoted
to active/master only by activate (domain-model-design §31/§32/§39-41).
"""

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

CHARACTER_STATUSES = ("active", "archived")
CHARACTER_VERSION_STATUSES = ("active", "stale", "archived")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    alias: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(Text)
    age_description: Mapped[str | None] = mapped_column(Text)
    appearance: Mapped[str | None] = mapped_column(Text)
    personality: Mapped[str | None] = mapped_column(Text)
    visual_prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    default_costume_id: Mapped[str | None] = mapped_column(Text)  # weak ref until costumes table lands

    # P2-T008: authoritative MASTER pointer (ADR-002 pattern) — nullable until a
    # version is activated. New shots bind master_version_id; old shots are NOT updated.
    master_version_id: Mapped[str | None] = mapped_column(ForeignKey("character_versions.id"))

    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency (§88)

    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class CharacterVersion(Base):
    """Character visual version (P2-T007): a versioned representative reference Asset.

    Immutable chain: edits create vN+1. Group-scoped version_number (max+1), unique
    index backstop, soft-deleted rows excluded from version_number computation.
    status: active (the current MASTER) | stale (superseded) | archived.
    """

    __tablename__ = "character_versions"
    __table_args__ = (
        # only one version_number per character among non-deleted rows
        Index("uq_character_versions_number", "character_id", "version_number", unique=True),
        Index("ix_character_versions_asset_id", "asset_id"),
    )

    id: Mapped[str] = uuid_pk()
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)  # representative visual asset
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="stale")  # active|stale|archived
    checksum: Mapped[str | None] = mapped_column(Text)

    deleted_at: Mapped[str | None] = mapped_column(Text)  # soft delete (draft versions)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class ShotCharacter(Base):
    """Shot ↔ Character link (database-v0.1 §11) — one shot can hold several characters."""

    __tablename__ = "shot_characters"
    __table_args__ = (
        # P1-E1-T02: a character appears at most once per shot
        Index("uq_shot_characters_pair", "shot_id", "character_id", unique=True),
    )

    id: Mapped[str] = uuid_pk()
    shot_id: Mapped[str] = mapped_column(ForeignKey("shots.id"), nullable=False, index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False, index=True)

    # P2-T010: costume_id weak ref into costumes (no hard FK on link rows so shot
    # assignment stays optional — validated service-side, consistent with scenes.location_id).
    costume_id: Mapped[str | None] = mapped_column(Text)
    # continuity fields (future Stage: filled by AI Director / continuity checks)
    role: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    pose: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(Text)
    screen_direction: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = ts_created()
