"""Project model (database-v0.1 §3)."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

PROJECT_STATUSES = ("draft", "active", "archived", "completed")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")  # draft|active|archived|completed
    style_config: Mapped[str | None] = mapped_column(Text)  # JSON
    default_language: Mapped[str | None] = mapped_column(Text)
    aspect_ratio: Mapped[str | None] = mapped_column(Text)  # e.g. "9:16"
    fps: Mapped[int | None] = mapped_column()
    cover_path: Mapped[str | None] = mapped_column(Text)  # relative path under projects/{id}/
    deleted_at: Mapped[str | None] = mapped_column(Text)  # soft delete (database-v0.1 §41)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
