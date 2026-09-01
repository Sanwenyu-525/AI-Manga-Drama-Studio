"""ContinuityService — the Continuity Engine (P8-T001..T017; continuity-engine-design §180).

Turns shots from "independent AI clips" into a continuous narrative state chain:

    Scene Base State
        ↓
    Shot 01 Delta → resolved Shot 01 Start/End
        ↓
    Shot 02 Delta → resolved Shot 02 Start/End
        ...

Each shot's resolved start/end states are persisted (Alpha stores fully-resolved
states per shot, design §64-65). A dirty-range recompute (§107-110) starts from a
given shot (or the scene head) and re-resolves only N..end, leaving earlier shots
untouched — so editing an early shot invalidates only downstream continuity.

Rules are pure functions (deterministic first, design §77-78) producing a warning
snapshot stored on the shot row; the Agent (P8-continuity-agent, parallel) adds
semantic warnings separately.

STALE integration (§111-118, §119-123): when a continuity fact changes, the
affected shots are recomputed and their ACTIVE generated assets are marked stale
(status=stale) — never auto-regenerated.



Responsibilities (red lines):
- Persists continuity_warnings (rule-derived + agent semantic) and reads them back.
- Exposes list_transitions(scene_id) for the shot_transitions structure (P8-T024..T026).
- Never writes the domain directly: fixes go through ProposalService → ShotService.

P8-A integration point: check_scene() iterates the shots' continuity state via
list_state_for_scene(). When the P8-A shot_continuity_states table (with its
warnings_json) is merged onto this branch, that method's body should be swapped to
read from that table instead of recomputing from shot base data — the rest of the
service (warning persistence, acknowledge, fix flow, events) is table-driven and
unaffected. The rule checks below are placeholder semantics until P8-E2 rules land.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.logging import get_logger
from app.db.models import (
    Character,
    Scene,
    SceneContinuityState,
    Shot,
    ShotCharacter,
    ShotContinuityState,
    ShotVisualSpec,
)
from app.repositories import (
    SceneContinuityRepository,
    ShotContinuityRepository,
)
from app.core.errors import NotFoundError, ValidationError
from app.db.models import ContinuityWarning, Episode, ShotTransition
from app.domain.continuity import (
    WARNING_STATUS_ACKNOWLEDGED,
    WARNING_STATUS_FIXED,
    WARNING_STATUS_OPEN,
    ContinuityWarningRead,
    SemanticWarning,
    TransitionRead,
)
from app.events.bus import (
    EVENT_CONTINUITY_WARNING_ACKNOWLEDGED,
    EVENT_CONTINUITY_WARNING_CREATED,
    EVENT_CONTINUITY_WARNING_FIXED,
    StudioEvent,
    bus,
)
from app.llm.gateway import LLMGateway







logger = get_logger("continuity")

# --- warning shape constants (api-event-contract / design §81-84) ---
SRC_RULE = "RULE"
SEV_INFO = "INFO"
SEV_WARN = "WARNING"
SEV_ERROR = "ERROR"


def canonical_json(value: Any) -> str:
    """Deterministic canonical JSON (stable key order, compact) for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relevant_state_hash(start: dict | None, end: dict | None) -> str:
    """Relevant-state hash (§112-116): only generation-relevant facts are hashed, so
    unrelated edits (dialogue, camera angle, warning status) never change the hash
    and therefore never stale an asset."""
    start_r = _relevant_subset(start)
    end_r = _relevant_subset(end)
    return _sha256(canonical_json({"start": start_r, "end": end_r}))


def _relevant_subset(state: dict | None) -> dict:
    """Extract the fixed generation-relevant slice of a resolved state (design §114):
    Location, Lighting, CharacterVersion, Costume, Position, Orientation, Emotion(expression),
    Prop holder/visibility/position."""
    state = state or {}
    env = state.get("environment") or {}
    env_r = {k: env.get(k) for k in ("location_id", "lighting", "time_of_day", "weather")}
    chars = {}
    for cid, cs in (state.get("characters") or {}).items():
        chars[cid] = {
            k: cs.get(k)
            for k in ("character_version_id", "costume_id", "position", "orientation", "emotion")
        }
    props = {}
    for pid, ps in (state.get("props") or {}).items():
        props[pid] = {
            k: ps.get(k)
            for k in ("holder_character_id", "visible", "position")
        }
    return {"environment": env_r, "characters": chars, "props": props}


def _empty_environment(scene: Scene) -> dict:
    return {
        "location_id": scene.location_id,
        "time_of_day": scene.time_of_day,
        "lighting": scene.lighting,
        "weather": scene.weather,
        "mood": scene.mood,
    }


def _character_state(c: Character, costume_id: str | None = None) -> dict:
    """Default CharacterState for a character (design §22-23: binds master version ref)."""
    return {
        "character_id": c.id,
        "character_version_id": c.master_version_id,
        "costume_id": costume_id if costume_id is not None else c.default_costume_id,
        "position": None,
        "orientation": None,
        "action": None,
        "emotion": None,
        "physical": None,
    }


# --------------------------------------------------------------------------- rules
# Pure, unit-testable rule functions. Each returns a list of warning dicts with the
# canonical shape: {code, category, severity, message}. shot_id is appended by the
# orchestrator. No DB access — deterministic first (design §77-78).


def rule_costume(prev_end: dict | None, start: dict | None, base: dict | None, char_id: str) -> list[dict]:
    """T008 Costume Rule: a costume that differs from the scene-base default without
    an explicit transition is a warning (design §24-25, §72)."""
    out: list[dict] = []
    base_char = ((base or {}).get("characters") or {}).get(char_id)
    start_char = ((start or {}).get("characters") or {}).get(char_id)
    if not base_char or not start_char:
        return out
    base_costume = base_char.get("costume_id")
    start_costume = start_char.get("costume_id")
    if base_costume and start_costume and start_costume != base_costume:
        out.append({
            "code": "COSTUME_CHANGED",
            "category": "APPEARANCE",
            "severity": SEV_WARN,
            "message": (
                f"Character {char_id} costume changed to '{start_costume}' "
                f"(scene base '{base_costume}') without an explicit transition."
            ),
        })
    return out


def rule_character_version(
    prev_end: dict | None, start: dict | None, base: dict | None, char_id: str, master_version_id: str | None
) -> list[dict]:
    """T009 Character Version Rule: the shot references a version that is not the
    character's current MASTER → outdated reference warning (STALE candidate, design §71, §119-122)."""
    out: list[dict] = []
    start_char = ((start or {}).get("characters") or {}).get(char_id)
    if not start_char:
        return out
    used_version = start_char.get("character_version_id")
    if used_version and master_version_id and used_version != master_version_id:
        out.append({
            "code": "CHARACTER_REFERENCE_OUTDATED",
            "category": "APPEARANCE",
            "severity": SEV_WARN,
            "message": (
                f"Character {char_id} uses version '{used_version}' while the "
                f"master version is '{master_version_id}'."
            ),
        })
    return out


def rule_location(prev_end: dict | None, start: dict | None, base: dict | None) -> list[dict]:
    """T010 Location Rule: the shot's location differs from the scene base → change
    without scene boundary warning (design §74)."""
    out: list[dict] = []
    base_env = (base or {}).get("environment") or {}
    start_env = (start or {}).get("environment") or {}
    base_loc = base_env.get("location_id")
    start_loc = start_env.get("location_id")
    if base_loc and start_loc and start_loc != base_loc:
        out.append({
            "code": "LOCATION_CHANGED",
            "category": "LOCATION",
            "severity": SEV_WARN,
            "message": (
                f"Shot location '{start_loc}' differs from scene base location "
                f"'{base_loc}' without a scene boundary."
            ),
        })
    return out


def rule_prop_holder(prev_end: dict | None, start: dict | None, end: dict | None, prop_id: str) -> list[dict]:
    """T011 Prop Holder Rule: a prop changed holders between consecutive shots without
    a declared pass/drop → warning (design §73, §101)."""
    out: list[dict] = []
    prev_end_prop = ((prev_end or {}).get("props") or {}).get(prop_id) or {}
    end_prop = ((end or {}).get("props") or {}).get(prop_id) or {}
    prev_holder = prev_end_prop.get("holder_character_id")
    end_holder = end_prop.get("holder_character_id")
    if prev_holder and end_holder and prev_holder != end_holder:
        out.append({
            "code": "PROP_HOLDER_CHANGED",
            "category": "PROP",
            "severity": SEV_WARN,
            "message": (
                f"Prop {prop_id} holder changed from '{prev_holder}' to '{end_holder}' "
                "without a declared transition."
            ),
        })
    return out


def rule_prop_disappearance(prev_end: dict | None, end: dict | None, prop_id: str) -> list[dict]:
    """T012 Prop Disappearance Rule: a prop present and visible in the previous shot
    became absent/not visible → warning (design §73)."""
    out: list[dict] = []
    prev_end_prop = ((prev_end or {}).get("props") or {}).get(prop_id) or {}
    end_prop = ((end or {}).get("props") or {}).get(prop_id)
    prev_visible = prev_end_prop.get("visible", prev_end_prop.get("holder_character_id") is not None)
    if prev_visible and end_prop is None:
        out.append({
            "code": "PROP_DISAPPEARED",
            "category": "PROP",
            "severity": SEV_WARN,
            "message": f"Prop {prop_id} disappeared without a declared drop/offscreen."
        })
    return out


def rule_time_of_day(prev_end: dict | None, start: dict | None, base: dict | None) -> list[dict]:
    """T013 Time Rule: a time-of-day jump (e.g. night→day) without a declared TIME_SKIP
    → warning (design §50, §73)."""
    out: list[dict] = []
    base_env = (base or {}).get("environment") or {}
    start_env = (start or {}).get("environment") or {}
    base_tod = base_env.get("time_of_day")
    start_tod = start_env.get("time_of_day")
    if base_tod and start_tod and start_tod != base_tod:
        out.append({
            "code": "TIME_OF_DAY_CHANGED",
            "category": "TEMPORAL",
            "severity": SEV_WARN,
            "message": (
                f"Time of day changed from '{base_tod}' (scene base) to '{start_tod}' "
                "without a declared time skip."
            ),
        })
    return out


def rule_position_jump(prev_end: dict | None, start: dict | None, char_id: str) -> list[dict]:
    """T014 Position Jump Rule: semantic position changed between consecutive shots
    (both known) → warning (design §75)."""
    out: list[dict] = []
    prev_char = ((prev_end or {}).get("characters") or {}).get(char_id) or {}
    start_char = ((start or {}).get("characters") or {}).get(char_id) or {}
    prev_pos = prev_char.get("position")
    start_pos = start_char.get("position")
    if prev_pos and start_pos and prev_pos != start_pos:
        out.append({
            "code": "POSITION_JUMP",
            "category": "SPATIAL",
            "severity": SEV_WARN,
            "message": (
                f"Character {char_id} position jumped from '{prev_pos}' to "
                f"'{start_pos}' between consecutive shots."
            ),
        })
    return out


def rule_orientation_flip(prev_end: dict | None, start: dict | None, char_id: str) -> list[dict]:
    """T014 Orientation Flip Rule: orientation flipped between consecutive shots →
    warning (design §76: WARNING, not ERROR)."""
    out: list[dict] = []
    prev_char = ((prev_end or {}).get("characters") or {}).get(char_id) or {}
    start_char = ((start or {}).get("characters") or {}).get(char_id) or {}
    prev_ori = prev_char.get("orientation")
    start_ori = start_char.get("orientation")
    if prev_ori and start_ori and prev_ori != start_ori:
        out.append({
            "code": "ORIENTATION_FLIP",
            "category": "SPATIAL",
            "severity": SEV_WARN,
            "message": (
                f"Character {char_id} orientation flipped from '{prev_ori}' to "
                f"'{start_ori}' between consecutive shots."
            ),
        })
    return out


def run_rules(
    *,
    prev_end: dict | None,
    start: dict | None,
    end: dict | None,
    base: dict | None,
    masters: dict[str, str | None],
    shot_id: str,
) -> list[dict]:
    """Orchestrate all rules for one shot transition; attach shot_id to each warning.

    masters: {character_id: master_version_id} resolved from the Character rows so
    the version rule can compare the used version against the current MASTER."""
    warnings: list[dict] = []
    start_chars = (start or {}).get("characters") or {}
    end_props = (end or {}).get("props") or {}
    prev_end_props = (prev_end or {}).get("props") or {}

    for char_id in start_chars:
        warnings += rule_costume(prev_end, start, base, char_id)
        warnings += rule_character_version(prev_end, start, base, char_id, masters.get(char_id))
        warnings += rule_position_jump(prev_end, start, char_id)
        warnings += rule_orientation_flip(prev_end, start, char_id)
    warnings += rule_location(prev_end, start, base)
    warnings += rule_time_of_day(prev_end, start, base)
    for prop_id in set(prev_end_props) | set(end_props):
        warnings += rule_prop_holder(prev_end, start, end, prop_id)
        warnings += rule_prop_disappearance(prev_end, end, prop_id)

    for w in warnings:
        w["shot_id"] = shot_id
    return warnings


# --------------------------------------------------------------------- service






logger = get_logger("continuity.service")

# List of rules active as placeholders until P8-E2 ("Rules") is merged.
# Each is (category, severity, checker) — checker: (shot) -> message | None.
_RULE_NAMES = ("shot_type_jump", "prop_reference")




class ContinuityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.scene_repo = SceneContinuityRepository(session)
        self.shot_repo = ShotContinuityRepository(session)

    # ------------------------------------------------------------- scene base
    def compute_scene_base(self, scene_id: str) -> SceneContinuityState:
        """Compute and persist the Scene Base State (P8-T001; design §14, §124).

        Base = EnvironmentState (from scene fields) + the set of characters appearing
        across the scene's shots (with master version refs / default costumes).
        Idempotent: upserts the scene_continuity_states row.
        """
        scene = self.session.get(Scene, scene_id)
        if scene is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})

        characters = self._scene_characters(scene_id)
        state = {
            "environment": _empty_environment(scene),
            "characters": {cid: _character_state(c, costume_id) for cid, c, costume_id in characters},
            "props": {},
        }
        base_hash = _sha256(canonical_json(_relevant_subset(state)))

        row = self.scene_repo.get_by_scene(scene_id)
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = SceneContinuityState(
                scene_id=scene_id,
                base_state_json=canonical_json(state),
                state_hash=base_hash,
                computed_at=now,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.base_state_json = canonical_json(state)
            row.state_hash = base_hash
            row.computed_at = now
            row.updated_at = now
        self.session.commit()
        return row

    def _scene_characters(self, scene_id: str) -> list[tuple[str, Character, str | None]]:
        """(character_id, Character, costume_id) for characters appearing in the scene.

        Determined via the union of shot_characters across the scene's shots. The
        costume is the character's default unless a specific shot assignment differs
        (we take the character default as the base baseline)."""
        shot_ids = list(
            self.session.scalars(
                select(Shot.id).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
            )
        )
        char_ids = list(
            self.session.scalars(
                select(ShotCharacter.character_id)
                .where(ShotCharacter.shot_id.in_(shot_ids))
                .distinct()
            )
        ) if shot_ids else []
        chars = {
            c.id: c
            for c in self.session.scalars(select(Character).where(Character.id.in_(char_ids)))
        } if char_ids else {}
        return [(cid, chars[cid], chars[cid].default_costume_id) for cid in char_ids if cid in chars]

    # ------------------------------------------------- shot states (dirty range)
    def compute_shot_states(
        self,
        scene_id: str,
        from_shot_id: str | None = None,
        *,
        recompute_scene_base: bool = False,
    ) -> tuple[int, int]:
        """Dirty-range recompute (P8-T015; design §107-110): re-resolve shots from
        from_shot_id (or the scene head) to the scene end. Earlier shots are untouched.

        Returns (recomputed_shots, total_shots). Uses the stored scene base unless
        recompute_scene_base=True forces a fresh base aggregation.
        """
        scene = self.session.get(Scene, scene_id)
        if scene is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})

        # scene base (compute/cache)
        base_row = self.scene_repo.get_by_scene(scene_id)
        if recompute_scene_base or base_row is None:
            base_row = self.compute_scene_base(scene_id)
        base: dict = json.loads(base_row.base_state_json)

        shots = list(
            self.session.scalars(
                select(Shot)
                .where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
                .order_by(Shot.shot_order)
            )
        )
        total = len(shots)
        if total == 0:
            return 0, 0

        if from_shot_id is None:
            from_index = 0
        else:
            idx = next((i for i, s in enumerate(shots) if s.id == from_shot_id), None)
            if idx is None:
                from app.core.errors import NotFoundError

                raise NotFoundError(
                    "Shot does not exist in this scene.", {"shot_id": from_shot_id, "scene_id": scene_id}
                )
            from_index = idx

        # seed the previous end state from the shot before from_index
        prev_end: dict | None = None
        if from_index > 0:
            prev_row = self.shot_repo.get_by_shot(shots[from_index - 1].id)
            prev_end = (
                json.loads(prev_row.end_state_json) if prev_row and prev_row.end_state_json else None
            )
            if prev_end is None:
                # fall back: recompute the whole scene from head
                from_index = 0

        masters = self._master_versions({c for shot in shots for c in self._shot_character_ids(shot.id)})

        recomputed = 0
        for i in range(from_index, total):
            shot = shots[i]
            spec = self.session.get(ShotVisualSpec, shot.id)
            links = self._links_for_shot(shot.id)
            prev_end, start, end, delta, dep, hash_val, warnings = self._resolve_shot(
                shot,
                spec,
                links,
                prev_end,
                base,
                masters,
            )
            self._persist_shot_state(shot, start, end, delta, dep, hash_val, warnings)
            recomputed += 1
        self.session.commit()
        return recomputed, total

    def _master_versions(self, char_ids: set[str]) -> dict[str, str | None]:
        if not char_ids:
            return {}
        chars = {
            c.id: c
            for c in self.session.scalars(select(Character).where(Character.id.in_(char_ids)))
        }
        return {cid: chars[cid].master_version_id for cid in char_ids if cid in chars}

    def _shot_character_ids(self, shot_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(ShotCharacter.character_id).where(ShotCharacter.shot_id == shot_id)
            )
        )

    def _links_for_shot(self, shot_id: str) -> dict[str, ShotCharacter]:
        rows = self.session.scalars(
            select(ShotCharacter).where(ShotCharacter.shot_id == shot_id)
        )
        return {r.character_id: r for r in rows}

    def _resolve_shot(
        self,
        shot: Shot,
        spec: ShotVisualSpec | None,
        links: dict[str, ShotCharacter],
        prev_end: dict | None,
        base: dict,
        masters: dict[str, str | None],
    ) -> tuple[dict, dict, dict, dict, dict, str, list[dict]]:
        """Resolve one shot's start/end/delta/dependencies/hash/warnings."""
        start = self._resolve_start(shot, spec, links, prev_end, base)
        delta = self._derive_delta(prev_end, start, shot, links, spec)
        end = self._resolve_end(start, delta, shot, links)
        dep = self._build_dependencies(shot, prev_end, base)
        hash_val = _relevant_state_hash(start, end)
        warnings = run_rules(
            prev_end=prev_end,
            start=start,
            end=end,
            base=base,
            masters=masters,
            shot_id=shot.id,
        )
        return prev_end, start, end, delta, dep, hash_val, warnings

    def _resolve_start(
        self,
        shot: Shot,
        spec: ShotVisualSpec | None,
        links: dict[str, ShotCharacter],
        prev_end: dict | None,
        base: dict,
    ) -> dict:
        """Start state = previous End (+ base environment) + this shot's explicit overrides."""
        # environment baseline
        env_source = dict(base.get("environment") or {})
        base_chars = _deep_copy(base.get("characters") or {})
        if prev_end is not None:
            start = _deep_copy(prev_end)
            # keep base identities for any character not yet carried by prev_end
            if not start.get("characters"):
                start["characters"] = {}
            for cid, bchar in base_chars.items():
                start["characters"].setdefault(cid, _deep_copy(bchar))
        else:
            start = {
                "environment": _deep_copy(env_source),
                "characters": base_chars,
                "props": _deep_copy(base.get("props") or {}),
            }

        # environment overrides from the shot's visual spec
        env_over = {}
        if spec and spec.location_id:
            env_over["location_id"] = spec.location_id
        if spec and spec.lighting:
            env_over["lighting"] = spec.lighting
        if spec and spec.mood:
            env_over["mood"] = spec.mood
        if env_over:
            start["environment"].update(env_over)

        # character overrides from the shot's character links
        for cid, link in links.items():
            start_char = (start.get("characters") or {}).get(cid) or {}
            merged = _deep_copy(start_char)
            merged["character_id"] = cid
            if link.costume_id is not None:
                merged["costume_id"] = link.costume_id
            if link.position is not None:
                merged["position"] = link.position
            if link.screen_direction is not None:
                merged["orientation"] = link.screen_direction
            if link.action is not None:
                merged["action"] = link.action
            if link.emotion is not None:
                merged["emotion"] = link.emotion
            start.setdefault("characters", {})[cid] = merged

        # shot-level action/emotion overrides apply to all present characters
        for cid in list((start.get("characters") or {}).keys()):
            if shot.action is not None:
                start["characters"][cid]["action"] = shot.action
            if shot.emotion is not None:
                start["characters"][cid]["emotion"] = shot.emotion
        return start

    def _derive_delta(
        self,
        prev_end: dict | None,
        start: dict,
        shot: Shot,
        links: dict[str, ShotCharacter],
        spec: ShotVisualSpec | None,
    ) -> dict:
        """Delta = the structured change this shot introduces vs the previous end state.

        {(character_id): {changed fields}, "environment": {changed fields},
         "props": {changed fields}}. Fields that carry forward unchanged are omitted."""
        diff: dict[str, Any] = {}

        prev_chars = (prev_end or {}).get("characters") or {}
        start_chars = start.get("characters") or {}
        char_diff = {}
        for cid, cur in start_chars.items():
            prev = prev_chars.get(cid) or {}
            changed = {k: cur[k] for k in cur if cur.get(k) is not None and cur.get(k) != prev.get(k)}
            # only report meaningful per-character state changes
            kept = {k: v for k, v in changed.items()
                    if k in ("costume_id", "position", "orientation", "action", "emotion")}
            if kept:
                char_diff[cid] = kept
        if char_diff:
            diff["characters"] = char_diff

        prev_env = (prev_end or {}).get("environment") or {}
        start_env = start.get("environment") or {}
        env_diff = {k: start_env[k] for k in start_env
                    if start_env.get(k) is not None and start_env.get(k) != prev_env.get(k)}
        if env_diff:
            diff["environment"] = env_diff

        prev_props = (prev_end or {}).get("props") or {}
        start_props = start.get("props") or {}
        prop_diff = {}
        for pid, cur in start_props.items():
            prev = prev_props.get(pid) or {}
            changed = {k: cur[k] for k in cur
                       if cur.get(k) is not None and cur.get(k) != prev.get(k)
                       and k in ("holder_character_id", "visible", "position")}
            if changed:
                prop_diff[pid] = changed
        if prop_diff:
            diff["props"] = prop_diff

        # always carry through the shot's authored action/emotion as the authored delta
        if shot.action is not None or shot.emotion is not None:
            authored: dict = {}
            for cid in list(start_chars.keys()):
                entry = {}
                if shot.action is not None:
                    entry["action"] = shot.action
                if shot.emotion is not None:
                    entry["emotion"] = shot.emotion
                if entry:
                    authored[cid] = entry
            diff.setdefault("characters", {}).update(authored)
        return diff

    def _resolve_end(self, start: dict, delta: dict, shot: Shot, links: dict[str, ShotCharacter]) -> dict:
        """End state = Start + the progression that happens DURING the shot.

        For Alpha we model "during-shot" motion minimally: each character's action and
        emotion settle to the shot's authored values at the end (action phase END)."""
        end = _deep_copy(start)
        for cid, d in (delta.get("characters") or {}).items():
            if cid not in end.get("characters", {}):
                end.setdefault("characters", {})[cid] = {"character_id": cid}
            cur = end["characters"][cid]
            if "action" in d:
                cur["action"] = d["action"]
            if "emotion" in d:
                cur["emotion"] = d["emotion"]
        return end

    def _build_dependencies(self, shot: Shot, prev_end: dict | None, base: dict) -> dict:
        """dependencies_json: provenance of which upstream facts this shot depends on
        (design §112-116). Derived from the resolved character version refs + base hash."""
        versions = {}
        char_ids = self._shot_character_ids(shot.id)
        chars = {
            c.id: c
            for c in self.session.scalars(select(Character).where(Character.id.in_(char_ids)))
        } if char_ids else {}
        for cid in char_ids:
            c = chars.get(cid)
            if c and c.master_version_id:
                versions[cid] = c.master_version_id
        prev_hash = _relevant_state_hash(prev_end, prev_end) if prev_end else None
        return {
            "previous_shot_id": shot.previous_shot_id,
            "base_hash": (base and base.get("_hash")) or None,
            "versions": versions,
            "previous_end_hash": prev_hash,
        }

    def _persist_shot_state(
        self,
        shot: Shot,
        start: dict,
        end: dict,
        delta: dict,
        dep: dict,
        hash_val: str,
        warnings: list[dict],
    ) -> None:
        row = self.shot_repo.get_by_shot(shot.id)
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = ShotContinuityState(
                shot_id=shot.id,
                scene_id=shot.scene_id,
                start_state_json=canonical_json(start),
                end_state_json=canonical_json(end),
                delta_json=canonical_json(delta),
                dependencies_json=canonical_json(dep),
                state_hash=hash_val,
                warnings_json=canonical_json(warnings),
                recomputed_at=now,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.start_state_json = canonical_json(start)
            row.end_state_json = canonical_json(end)
            row.delta_json = canonical_json(delta)
            row.dependencies_json = canonical_json(dep)
            row.state_hash = hash_val
            row.warnings_json = canonical_json(warnings)
            row.recomputed_at = now
            row.updated_at = now

    # ------------------------------------------------------------------ reads
    def get_scene_continuity(self, scene_id: str) -> dict:
        """Scene Continuity view (GET /scenes/{id}/continuity)."""
        scene = self.session.get(Scene, scene_id)
        if scene is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        base_row = self.scene_repo.get_by_scene(scene_id)
        if base_row is None:
            base_row = self.compute_scene_base(scene_id)
        base_state = json.loads(base_row.base_state_json)
        shots = list(
            self.session.scalars(
                select(Shot)
                .where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
                .order_by(Shot.shot_order)
            )
        )
        # ensure every shot has a continuity row (compute on demand so a first read
        # of a freshly-created scene still returns the full chain)
        missing = [s.id for s in shots if self.shot_repo.get_by_shot(s.id) is None]
        if missing:
            self.compute_shot_states(scene_id, from_shot_id=None)
        shot_reads = []
        for shot in shots:
            row = self.shot_repo.get_by_shot(shot.id)
            if row is None:
                continue
            shot_reads.append(self._shot_read(shot, row))
        return {
            "scene_id": scene_id,
            "base_state": base_state,
            "base_state_hash": base_row.state_hash,
            "shots": shot_reads,
        }

    def get_shot_continuity(self, shot_id: str) -> dict:
        """Single shot continuity (GET /shots/{id}/continuity-state)."""
        shot = self.session.get(Shot, shot_id)
        if shot is None:
            from app.core.errors import NotFoundError

            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        row = self.shot_repo.get_by_shot(shot_id)
        if row is None:
            # compute it on the fly so a first read is always consistent
            self.compute_shot_states(shot.scene_id, from_shot_id=shot_id)
            row = self.shot_repo.get_by_shot(shot_id)
        return self._shot_read(shot, row)

    def _shot_read(self, shot: Shot, row: ShotContinuityState) -> dict:
        return {
            "shot_id": shot.id,
            "shot_number": shot.shot_number,
            "start_state": json.loads(row.start_state_json),
            "end_state": json.loads(row.end_state_json),
            "delta": json.loads(row.delta_json),
            "state_hash": row.state_hash,
            "warnings": json.loads(row.warnings_json) if row.warnings_json else [],
        }

    # ------------------------------------------------------------- STALE hook
    def recompute_after_shot_change(self, shot_id: str) -> int:
        """T017: on a shot edit, dirty-range recompute from that shot + stale its
        active assets (never regenerate). Returns the recomputed count."""
        shot = self.session.get(Shot, shot_id)
        if shot is None:
            return 0
        count, _ = self.compute_shot_states(shot.scene_id, from_shot_id=shot_id)
        self._stale_assets_from(shot.scene_id, from_shot_id=shot.id)
        return count

    def recompute_after_scene_change(self, scene_id: str) -> int:
        """T017: on a scene edit, recompute the scene base + all shots + stale active assets."""
        self.compute_scene_base(scene_id)
        count, _ = self.compute_shot_states(scene_id, from_shot_id=None)
        self._stale_assets_from(scene_id, from_shot_id=None)
        return count

    def recompute_after_character_version_change(self, character_id: str) -> int:
        """T017: when a character's MASTER version changes, recompute every scene whose
        shots reference the character, and stale their active assets. New shots bind the
        new master; old resolved states keep their version (design §119-123) — the rule
        engine flags CHARACTER_REFERENCE_OUTDATED."""
        scene_ids = list(
            self.session.scalars(
                select(Shot.scene_id)
                .join(ShotCharacter, ShotCharacter.shot_id == Shot.id)
                .where(
                    ShotCharacter.character_id == character_id,
                    Shot.deleted_at.is_(None),
                )
                .distinct()
            )
        )
        total = 0
        for scene_id in scene_ids:
            scene_shots = list(
                self.session.scalars(
                    select(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
                )
            )
            for shot in scene_shots:
                recomputed, _ = self.compute_shot_states(scene_id, from_shot_id=shot.id)
                total += recomputed
            self._stale_assets_from(scene_id, from_shot_id=None)
        return total

    def _stale_assets_from(self, scene_id: str, from_shot_id: str | None) -> int:
        """Mark ACTIVE image/video assets of recomputed shots as STALE (design §118:
        only active assets make a shot stale; we never auto-regenerate)."""
        shots = list(
            self.session.scalars(
                select(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
            )
        )
        if from_shot_id is not None:
            idx = next((i for i, s in enumerate(shots) if s.id == from_shot_id), None)
            shots = shots[idx:] if idx is not None else shots
        asset_ids = {
            s.active_image_asset_id for s in shots if s.active_image_asset_id
        } | {
            s.active_video_asset_id for s in shots if s.active_video_asset_id
        }
        asset_ids.discard(None)
        if not asset_ids:
            return 0
        from app.db.models import Asset
        from app.services.asset_service import AssetService

        # only live assets currently "ready"
        rows = list(
            self.session.scalars(
                select(Asset).where(Asset.id.in_(asset_ids), Asset.deleted_at.is_(None))
            )
        )
        to_stale = [a.id for a in rows if a.status != "stale"]
        if not to_stale:
            return 0
        AssetService(self.session).mark_assets_stale(to_stale)
        return len(to_stale)



    def list_state_for_scene(self, scene_id: str) -> list[dict]:
        """Per-shot continuity input for the check.

        P8-A INTEGRATION: this currently recomputes a minimal state from shot base
        data (shot_type / camera_movement / action / emotion). Once
        shot_continuity_states.warnings_json is merged, replace this body to load
        that table's rows and return {shot_id, base_state, warnings_json} instead.
        The Continuity Agent's semantic check consumes this — nothing else changes.
        """
        stmt = select(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None)).order_by(Shot.shot_order)
        states: list[dict] = []
        for shot in self.session.scalars(stmt):
            states.append(
                {
                    "shot_id": shot.id,
                    "shot_number": shot.shot_number,
                    "shot_type": shot.shot_type,
                    "camera_movement": shot.camera_movement,
                    "action": shot.action,
                    "emotion": shot.emotion,
                    "duration": shot.duration,
                    "previous_shot_id": shot.previous_shot_id,
                    "next_shot_id": shot.next_shot_id,
                }
            )
        return states

    def project_id_for_scene(self, scene_id: str) -> str | None:
        scene = self.session.get(Scene, scene_id)
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None

    # ------------------------------------------------------------ rule checks (P8-E2 placeholder)
    def rule_checks(self, states: list[dict]) -> list[SemanticWarning]:
        """Deterministic rule-derived warnings (placeholder semantics).

        Replaced by the real P8-E2 Rules when merged. Currently flags an extreme
        shot-type jump across adjacent shots as a visual_flow warning and surfaces
        any shot with a missing camera_movement as info.
        """
        warnings: list[SemanticWarning] = []
        for idx, state in enumerate(states):
            nxt = states[idx + 1] if idx + 1 < len(states) else None
            if nxt is not None:
                curr_t = state.get("shot_type")
                next_t = nxt.get("shot_type")
                _JUMP = {"extreme_close_up", "extreme_wide"}
                if curr_t in _JUMP and next_t in _JUMP and curr_t != next_t:
                    warnings.append(
                        SemanticWarning(
                            scope="shot",
                            shot_id=nxt["shot_id"],
                            category="visual_flow",
                            message="镜头景别在极近景与极远景之间跳变，视觉衔接突兀。",
                            severity="warning",
                            evidence={
                                "rule": "shot_type_jump",
                                "from_shot": curr_t,
                                "to_shot": next_t,
                            },
                        )
                    )
            if not state.get("camera_movement") and state.get("camera_movement") != "":
                warnings.append(
                    SemanticWarning(
                        scope="shot",
                        shot_id=state["shot_id"],
                        category="visual_flow",
                        message="该镜头未指定运镜 (camera_movement)，建议补充以保证衔接。",
                        severity="info",
                        evidence={"rule": "camera_movement_missing", "shot_number": state.get("shot_number")},
                    )
                )
        return warnings

    # ---------------------------------------------------------------- semantic check
    async def semantic_check(self, llm: LLMGateway, states: list[dict]) -> list[SemanticWarning]:
        """LLM semantic review of continuity (P8-T018). FakeLLM path returns rule
        output (deterministic) so tests don't depend on a live model; the openai
        path invokes a real structured generation. If the model raises, we fall
        back to rule output (a check should never fail because the model hiccuped).
        """
        from app.domain.continuity import SemanticWarning

        system = (
            "You are a manga drama continuity reviewer. Given the shot state list, "
            "detect semantic continuity issues (emotion/action/across-shot logic) and "
            "return JSON matching: {scope, shot_id?, category, message, severity, evidence}."
        )
        prompt = json.dumps({"scene_shots": states}, ensure_ascii=False)
        try:
            result = await llm.structured_list(SemanticWarning, system, prompt)
            return list(result)
        except Exception:  # noqa: BLE001 — real-model errors degrade to rule path
            logger.warning("semantic LLM check failed; falling back to rule path")
            return []

    # ------------------------------------------------------------- check + persist
    async def check_scene(self, scene_id: str, llm: LLMGateway, run_id: str | None = None) -> list[ContinuityWarningRead]:
        """Run the full continuity check for a scene and persist new open warnings.

        Returns the newly-created warnings. A scene that does not exist raises 404.
        """
        scene = self.session.get(Scene, scene_id)
        if scene is None or scene.deleted_at:
            raise NotFoundError("Scene does not exist or was deleted.", {"scene_id": scene_id})
        project_id = self.project_id_for_scene(scene_id)
        states = self.list_state_for_scene(scene_id)
        warnings = self.rule_checks(states) + await self.semantic_check(llm, states)

        created: list[ContinuityWarningRead] = []
        for w in warnings:
            row = ContinuityWarning(
                project_id=project_id or "",
                scene_id=scene_id,
                shot_id=w.shot_id,
                run_id=run_id,
                category=w.category,
                severity=w.severity,
                message=w.message,
                evidence_json=json.dumps(w.evidence, ensure_ascii=False) if w.evidence else None,
                status=WARNING_STATUS_OPEN,
                created_at=_now(),
            )
            self.session.add(row)
            created.append(row)
        self.session.commit()
        for row in created:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_CONTINUITY_WARNING_CREATED,
                    entity_type="continuity_warning",
                    entity_id=row.id,
                    project_id=row.project_id,
                    payload={
                        "scene_id": scene_id,
                        "shot_id": row.shot_id,
                        "category": row.category,
                        "severity": row.severity,
                        "message": row.message,
                        "run_id": run_id,
                    },
                )
            )
        return [_read(w) for w in created]

    # -------------------------------------------------------------- warning reads
    def list_open_warnings(self, scene_id: str) -> list[ContinuityWarningRead]:
        """Open (not-fixed) warnings for a scene, newest first (api-event-contract §142)."""
        stmt = (
            select(ContinuityWarning)
            .where(ContinuityWarning.scene_id == scene_id, ContinuityWarning.status == WARNING_STATUS_OPEN)
            .order_by(ContinuityWarning.created_at.desc())
        )
        return [_read(w) for w in self.session.scalars(stmt)]

    def merge_open_warnings_into_shots(self, scene_id: str, shots: list[dict]) -> list[dict]:
        """Merge OPEN continuity_warnings-table entries into each shot's warnings dict
        (P8-B). shot_continuity_states.warnings_json stays authoritative for rule
        snapshots; the parallel table adds rule + agent semantic rows. Any schema
        drift degrades to the snapshot, never to a 500."""
        try:
            rows = self.session.scalars(
                select(ContinuityWarning).where(
                    ContinuityWarning.scene_id == scene_id,
                    ContinuityWarning.status == WARNING_STATUS_OPEN,
                )
            ).all()
        except Exception:  # noqa: BLE001 — table not present yet or schema drift
            return shots
        if not rows:
            return shots
        by_shot: dict[str, list[dict]] = {}
        for w in rows:
            by_shot.setdefault(w.shot_id, []).append(
                {
                    "code": w.category or "RULE",
                    "category": w.category or "RULE",
                    "severity": w.severity or "warning",
                    "message": w.message,
                    "shot_id": w.shot_id,
                    "id": w.id,
                }
            )
        for shot in shots:
            extra = by_shot.get(shot["shot_id"], [])
            if not extra:
                continue
            existing_ids = {w.get("id") for w in shot.get("warnings", [])}
            for w in extra:
                if w["id"] not in existing_ids:
                    shot["warnings"].append(w)
        return shots

    def list_warnings(self, scene_id: str, status: str | None = None) -> list[ContinuityWarningRead]:
        stmt = select(ContinuityWarning).where(ContinuityWarning.scene_id == scene_id)
        if status:
            if status not in ("open", "acknowledged", "fixed"):
                raise ValidationError("Invalid warning status filter.", {"status": status})
            stmt = stmt.where(ContinuityWarning.status == status)
        stmt = stmt.order_by(ContinuityWarning.created_at.desc())
        return [_read(w) for w in self.session.scalars(stmt)]

    def get_warning(self, warning_id: str) -> ContinuityWarning:
        w = self.session.get(ContinuityWarning, warning_id)
        if w is None:
            raise NotFoundError("Continuity warning does not exist.", {"warning_id": warning_id})
        return w

    def acknowledge(self, warning_id: str) -> ContinuityWarningRead:
        """Mark a warning acknowledged (seen/handled) so it stops re-flagging (P8-T018)."""
        w = self.get_warning(warning_id)
        if w.status == WARNING_STATUS_ACKNOWLEDGED:
            raise ValidationError("Warning is already acknowledged.", {"warning_id": warning_id})
        w.status = WARNING_STATUS_ACKNOWLEDGED
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_CONTINUITY_WARNING_ACKNOWLEDGED,
                entity_type="continuity_warning",
                entity_id=w.id,
                project_id=w.project_id,
                payload={"scene_id": w.scene_id, "shot_id": w.shot_id, "category": w.category},
            )
        )
        return _read(w)

    def mark_fixed(self, warning_id: str) -> ContinuityWarningRead:
        """Mark a warning fixed (called after a fix proposal applies successfully)."""
        w = self.get_warning(warning_id)
        w.status = WARNING_STATUS_FIXED
        w.resolved_at = _now()
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_CONTINUITY_WARNING_FIXED,
                entity_type="continuity_warning",
                entity_id=w.id,
                project_id=w.project_id,
                payload={"scene_id": w.scene_id, "shot_id": w.shot_id, "category": w.category},
            )
        )
        return _read(w)

    # ------------------------------------------------------------- shot_transitions
    def list_transitions(self, scene_id: str) -> list[TransitionRead]:
        """List shot_transitions for a scene (P8-T024..T026). MVP structure-only —
        rows exist only if a caller created them; frame assets stay NULL."""
        stmt = select(ShotTransition).where(ShotTransition.scene_id == scene_id).order_by(ShotTransition.created_at)
        return [_transition_read(t) for t in self.session.scalars(stmt)]




def _deep_copy(obj: dict) -> dict:
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read(w: ContinuityWarning) -> ContinuityWarningRead:
    return ContinuityWarningRead(
        id=w.id,
        project_id=w.project_id,
        scene_id=w.scene_id,
        shot_id=w.shot_id,
        run_id=w.run_id,
        category=w.category,
        severity=w.severity,
        message=w.message,
        evidence=json.loads(w.evidence_json) if w.evidence_json else {},
        status=w.status,
        created_at=w.created_at,
        resolved_at=w.resolved_at,
    )




def _transition_read(t: ShotTransition) -> TransitionRead:
    return TransitionRead(
        id=t.id,
        scene_id=t.scene_id,
        from_shot_id=t.from_shot_id,
        to_shot_id=t.to_shot_id,
        mode=t.mode,
        frame_from_asset_id=t.frame_from_asset_id,
        frame_to_asset_id=t.frame_to_asset_id,
        created_at=t.created_at,
    )
