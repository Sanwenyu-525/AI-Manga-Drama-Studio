"""Generation provenance models (P3-T012/T013; ADR-001 §3).

generation_inputs: what a generation consumed — sparse rows keyed by role.
  Current write path emits PROMPT_VERSION (generation.prompt_version_id) and
  SHOT (generation.shot_id). CHARACTER_REFERENCE / LOCATION_REFERENCE and other
  input roles are added when CharacterVersion/LocationVersion land (P2).
generation_outputs: what a generation produced. PRIMARY KEY(generation_id, asset_id)
  supports one-generation → many-assets while keeping a fast reverse lookup
  (asset → generation). role='primary' is the fallback output (the visible image).
"""

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import uuid_pk

# Role taxonomy (P3-T012): consumed inputs / produced outputs.
# Input roles: PROMPT_VERSION, SHOT, CHARACTER_REFERENCE, LOCATION_REFERENCE, ...
# M1: CHARACTER_REFERENCE is actually written by GenerationService.create_generation
# (role="character_reference"; auto ShotCharacter→MASTER resolution + explicit override).
INPUT_ROLES = ("PROMPT_VERSION", "SHOT", "CHARACTER_REFERENCE")
# Output roles: primary (the generation's named output), plus future secondary outputs.
OUTPUT_ROLES = ("primary", "secondary", "mask", "upscale")


class GenerationInput(Base):
    __tablename__ = "generation_inputs"

    id: Mapped[str] = uuid_pk()
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("generations.id"), nullable=False, index=True
    )
    input_type: Mapped[str] = mapped_column(Text, nullable=False)  # prompt|reference|resource
    reference_type: Mapped[str | None] = mapped_column(Text)  # PROMPT_VERSION | SHOT | CHARACTER_REFERENCE ...
    reference_id: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[float] = mapped_column(nullable=False, default=1000.0)
    metadata_json: Mapped[str | None] = mapped_column(Text)


class GenerationOutput(Base):
    __tablename__ = "generation_outputs"
    __table_args__ = (
        PrimaryKeyConstraint("generation_id", "asset_id", name="pk_generation_outputs"),
    )

    generation_id: Mapped[str] = mapped_column(ForeignKey("generations.id"), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    role: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[float] = mapped_column(nullable=False, default=1000.0)
