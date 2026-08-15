"""Character + ShotCharacter models (database-v0.1 §7, §11; mvp-spec §105-BE).

Character stores the *identity* (name/appearance/personality); costumes are managed
separately (costumes table comes later — default_costume_id stays a weak Text ref).
ShotCharacter is the many-to-many link table with continuity-relevant per-shot
attributes (position/pose/emotion) — MVP only fills shot_id/character_id.
"""

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

CHARACTER_STATUSES = ("active", "archived")


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

    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency (§88)

    deleted_at: Mapped[str | None] = mapped_column(Text)
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

    # continuity fields (future Stage: filled by AI Director / continuity checks)
    costume_id: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    pose: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(Text)
    screen_direction: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = ts_created()
