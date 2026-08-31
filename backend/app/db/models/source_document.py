"""SourceDocument model (database-v0.1 §32.6, mvp-spec DOC-001).

Project-level source-archive: free-text setting documents (character_setting /
worldview / outline / novel_draft / other). These are the "原文事实" layer that
complements the structured entity libraries (characters/locations/costumes):
Agent analysis (analyze_episode / shot planning) injects a budgeted digest of
these documents so character recognition and continuity judgment have facts to
stand on instead of guessing.

- source_hash: SHA-256 prefix of content (analysis idempotency-key style); the
  Agent injection digest is derived from it, so a changed document changes the
  analysis key (re-preview semantics, mirroring P2-E1-T01 snapshots).
- revision: optimistic concurrency (§88); deleted_at: soft delete (§89).
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

# doc_type allowed values (validation also happens service-side).
DOCUMENT_TYPES = (
    "character_setting",
    "worldview",
    "outline",
    "novel_draft",
    "other",
)
DOCUMENT_STATUSES = ("active", "archived")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)

    doc_type: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Optional entity linkage — validated service-side to the same project (404/422),
    # consistent with costumes.character_id / shot_characters.costume_id weak-refs.
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"))
    costume_id: Mapped[str | None] = mapped_column(ForeignKey("costumes.id"))

    source_hash: Mapped[str | None] = mapped_column(Text)  # content SHA-256 prefix
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    revision: Mapped[int] = mapped_column(nullable=False, default=1)  # optimistic concurrency (§88)

    deleted_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()
