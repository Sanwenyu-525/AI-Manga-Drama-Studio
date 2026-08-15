"""MediaVersion model (database-v0.1 §19): immutable version per shot (image/video).

Rows are never updated; "Set Active" only flips is_active on the new row (and clears others).
"""

from sqlalchemy import ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, uuid_pk

MEDIA_TYPES = ("image", "video")


class MediaVersion(Base):
    __tablename__ = "media_versions"
    __table_args__ = (
        # P1-E1-T02: immutable version numbers per shot + at most one active version
        Index("uq_media_versions_shot_number", "shot_id", "media_type", "version_number", unique=True),
        Index("uq_media_versions_active", "shot_id", unique=True, sqlite_where=text("is_active = 1")),
    )

    id: Mapped[str] = uuid_pk()
    shot_id: Mapped[str] = mapped_column(ForeignKey("shots.id"), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False, default="image")
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_id: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0/1
    rating: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
