"""ContinuityService — continuity warnings + transcriptions for the Continuity Agent (P8).

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

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import ContinuityWarning, Episode, Scene, Shot, ShotTransition
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

logger = get_logger("continuity.service")

# List of rules active as placeholders until P8-E2 ("Rules") is merged.
# Each is (category, severity, checker) — checker: (shot) -> message | None.
_RULE_NAMES = ("shot_type_jump", "prop_reference")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ContinuityService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------ P8-A hook
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
