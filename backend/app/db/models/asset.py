"""Asset model (database-v0.1 §13, mvp-spec §19): every real file registered here."""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, uuid_pk

ASSET_TYPES = ("image", "video", "audio", "reference", "document", "workflow", "thumbnail", "other")


class Asset(Base):
    __tablename__ = "assets"

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
    source_generation_id: Mapped[str | None] = mapped_column(Text)  # provenance (database-v0.1 §2.7)
    deleted_at: Mapped[str | None] = mapped_column(Text)  # soft delete
    created_at: Mapped[str] = ts_created()
