"""Costume model (database-v0.1 §8, domain-model-design §33; P2-T010).

Costumes group clothing looks (校服 / 篮球队服 ...) that may optionally belong to a
character (characters.character_id). P2-T010 ships basic CRUD only — no version
system (that is a future CostumeVersion task, mirroring Character/CharacterVersion).
reference_asset_id is a nullable FK to an Asset (参考图); validates service-side.
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

COSTUME_STATUSES = ("active", "archived")


class Costume(Base):
    __tablename__ = "costumes"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))  # optional owner

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    visual_prompt: Mapped[str | None] = mapped_column(Text)
    reference_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))

    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency (§88)
    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
