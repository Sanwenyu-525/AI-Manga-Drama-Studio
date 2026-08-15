"""ShotVisualSpec model (database-v0.1 §10, domain-model-design #21-22, mvp-spec P2-T005).

The shot's *visual* specification lives in its own 1:1 row so the production
model can formalize composition / lighting / facial_expression / style / negative
instructions without cluttering the atomic shot record.

- 1:1 with shots: shot_id is the PRIMARY KEY (SQLite enforces one spec per shot).
- P2-T005 write-through: ShotService upserts this row in the SAME transaction
  whenever the shot is created or updated; reads prefer spec fields and fall back
  to the (now deprecated) inline shot columns when the spec is missing, so legacy
  rows created before this migration stay fully readable and editable.
- The legacy shot columns (shot_type/camera_angle/camera_movement/action/emotion/
  environment_description/...) are KEPT (marked deprecated) and NOT migrated —
  a later batch removes them once every consumer has switched to the spec.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated


class ShotVisualSpec(Base):
    """Formalized visual specification of a single shot (1:1 with shots.id)."""

    __tablename__ = "shot_visual_specs"

    shot_id: Mapped[str] = mapped_column(
        ForeignKey("shots.id"), primary_key=True
    )

    # --- framing ---
    shot_type: Mapped[str | None] = mapped_column(Text)          # wide|medium|close_up...
    camera_angle: Mapped[str | None] = mapped_column(Text)       # eye_level|low_angle...
    camera_movement: Mapped[str | None] = mapped_column(Text)    # static|pan|dolly...
    composition: Mapped[str | None] = mapped_column(Text)        # rule_of_thirds|centered...

    # --- world / staging ---
    location_id: Mapped[str | None] = mapped_column(Text)  # FK→locations (Phase 2 table)
    lighting: Mapped[str | None] = mapped_column(Text)
    mood: Mapped[str | None] = mapped_column(Text)

    # --- performance ---
    action: Mapped[str | None] = mapped_column(Text)
    facial_expression: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)

    # --- generation directives ---
    style_instructions: Mapped[str | None] = mapped_column(Text)
    negative_instructions: Mapped[str | None] = mapped_column(Text)

    # --- extensibility (domain-model-design §22 "metadata") ---
    metadata_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()

    # --- mapping helpers (P2-T005 read preference / write-through) ---

    def mapped_read_dict(self) -> dict:
        """Project the spec onto the deprecated inline-shot field names so reads
        can uniformly prefer spec values and fall back to legacy columns."""
        return {
            "shot_type": self.shot_type,
            "camera_angle": self.camera_angle,
            "camera_movement": self.camera_movement,
            "action": self.action,
            "emotion": self.mood,  # spec.mood ↔ shot.emotion (legacy)
        }
