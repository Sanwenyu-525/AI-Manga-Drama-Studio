"""Continuity models (database-v0.1 §20-21, continuity-engine-design §11-45).

Continuity turns independent AI clips into a continuous narrative state chain:

- scene_continuity_states: ONE row per scene holding the Scene Base State
  (environment/时间/角色集合/道具集合 + state_hash) — the default "world" every
  shot in the scene starts from (design §14 Scene Base State).
- shot_continuity_states: ONE row per shot holding the resolved Shot Start / End
  states, the Shot Delta, dependencies (relevant state hashes), the relevant-state
  hash used for STALE detection, and a warnings_json snapshot produced by the rule
  engine during recompute (design §15-20, §108-116).

JSON serialization (design §22-39):
  EnvironmentState {location_id, time_of_day, lighting, weather, mood}
  CharacterState   {character_id, character_version_id, costume_id, position,
                    orientation, action, emotion, physical}
  PropState        {prop_id, holder_character_id, visible, position}

P8-T018/T019: continuity_warnings is the durable store of both Rule-derived and
Agent (semantic) warnings. The Agent NEVER flags issues / applies fixes directly —
it produces structured warnings here, and fixes go through the P7 Proposal system
(same WAITING_HUMAN approval flow), applied through ShotService.

P8-T021..T026 (Video Bridge structure): shot_transitions anticipates how adjacent
shots connect (LAST_TO_FIRST / REFERENCE_ONLY / CUT ...) and which frame assets are
references. MVP video generation is NOT implemented — this is structure-only: the
frame_*_asset_id columns stay NULL until real frame extraction (T021-T023) exists.

The *_json columns are TEXT holding canonical JSON (deterministic serialization so
hashes are stable across recomputes). All timestamps are TEXT ISO8601 UTC.
"""

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

# Warning lifecycle (design continuity-engine §83: OPEN / ACKNOWLEDGED / ...).
# Alpha keeps three states; IGNORED/INVALID map to acknowledged+resolved bookkeeping.
WARNING_STATUSES = ("open", "acknowledged", "fixed")

# Compliance with design §84: severity INFO / WARNING / ERROR (BLOCKING discouraged).
WARNING_SEVERITIES = ("info", "warning", "error")

# Transition modes for adjacent-shot connections (P8-T024..T026).
TRANSITION_MODES = ("LAST_TO_FIRST", "REFERENCE_ONLY", "CUT")


class SceneContinuityState(Base):
    """Scene Base State (design §14, §124) — one row per scene.

    base_state_json holds the scene-level baseline (EnvironmentState + the set of
    characters present at scene start with their default costume / master version
    references). state_hash is the relevant-state hash for STALE detection.
    """

    __tablename__ = "scene_continuity_states"

    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id"), primary_key=True
    )

    base_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    state_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    computed_at: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class ShotContinuityState(Base):
    """Resolved Shot Start/End + Delta + dependencies + warnings (design §20, §65).

    start_state_json / end_state_json are fully resolved states (base + inherited +
    delta applied), per design §64-65 (Alpha stores resolved Start/End per shot).
    dependencies_json records the hashes of the relevant upstream facts this shot
    depends on (the previous shot's end state + character/location version refs),
    which is what the relevant state_hash derives from for STALE detection (§112-116).
    """

    __tablename__ = "shot_continuity_states"

    shot_id: Mapped[str] = mapped_column(ForeignKey("shots.id"), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)

    start_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    end_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    delta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    dependencies_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # relevant-state hash (§115-116): stable while generation-relevant facts are
    # unchanged, so unrelated edits (e.g. warning status) never stale an Asset.
    state_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # rule-engine warning snapshot (source=RULE) captured at recompute time
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    recomputed_at: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class ContinuityWarning(Base):
    """One continuity issue flagged for a scene (rule or agent semantic, P8-T018)."""

    __tablename__ = "continuity_warnings"
    __table_args__ = (
        Index("ix_continuity_warnings_scene_status", "scene_id", "status"),
    )

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    shot_id: Mapped[str | None] = mapped_column(ForeignKey("shots.id"))
    run_id: Mapped[str | None] = mapped_column(Text)  # continuity_check agent run that produced it
    category: Mapped[str] = mapped_column(Text, nullable=False)  # costume|prop|location|time|emotion|visual_flow|...
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="warning")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    created_at: Mapped[str] = ts_created()
    resolved_at: Mapped[str | None] = mapped_column(Text)


class ShotTransition(Base):
    """Adjacent-shot connection record (P8-T024..T026 structure; database-v0.1 §21).

    Structure-only for MVP: no frame extraction / video generation yet, so the
    frame_*_asset_id referential pointers default to NULL until P8-T021..T023 land.
    """

    __tablename__ = "shot_transitions"
    __table_args__ = (
        Index("ix_shot_transitions_scene", "scene_id"),
    )

    id: Mapped[str] = uuid_pk()
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    from_shot_id: Mapped[str] = mapped_column(ForeignKey("shots.id"), nullable=False, index=True)
    to_shot_id: Mapped[str | None] = mapped_column(ForeignKey("shots.id"))  # NULL = scene boundary
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="CUT")
    frame_from_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    frame_to_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    created_at: Mapped[str] = ts_created()
