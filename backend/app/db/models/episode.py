"""Episode model (database-v0.1 §4)."""

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

EPISODE_STATUSES = ("draft", "analyzed", "planned", "generating", "done")


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("project_id", "episode_number", name="uq_episodes_project_number"),
    )

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str | None] = mapped_column(Text)  # original novel/screenplay text
    script_text: Mapped[str | None] = mapped_column(Text)  # structured/rewritten script
    summary: Mapped[str | None] = mapped_column(Text)
    analysis_key: Mapped[str | None] = mapped_column(Text)  # P1-E1-T01: idempotency key of the last episode analysis (source hash)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    deleted_at: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
