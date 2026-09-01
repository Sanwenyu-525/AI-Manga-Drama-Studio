"""ChangeSetService (P2-E3-T03 + P4-E3-T02) — readable, undoable records of mutations.

Red lines honored:
- Domain writes go through ShotService / VersionService / TimelineService —
  never raw ORM updates of content (only bookkeeping columns of the change-set
  rows themselves).
- Undo is a NEW compensating change, never a history edit: the original row is
  only flipped (undone=True) and linked to the compensating row; the entity gets
  revision+1 via the normal update path, so its updated events keep flowing.
- Minimal before/after patches only — never a copy of the whole entity.

Scope (P2-E3-T03): Director shot patches and active-version switches.
P4-E3-T02 (AC-2): user Timeline edits are recorded with source="timeline" so
they flow through the SAME undo machinery (entity_type="timeline_clip").
Other entity kinds are rejected, not guessed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import AgentChangeSet, Episode, Scene, Shot, TimelineClip
from app.domain.agent import ChangeSetRead
from app.domain.shot import ShotUpdate
from app.domain.timeline import TimelineClipUpdatePatch
from app.events.bus import (
    EVENT_AGENT_CHANGE_SET_CREATED,
    EVENT_AGENT_CHANGE_SET_UNDONE,
    EVENT_SHOT_ACTIVE_VERSION_CHANGED,
    StudioEvent,
    bus,
)
from app.services.shot_service import ShotService
from app.services.version_service import VersionService

logger = get_logger("agent.change_set")

# ChangeSet "field payloads" are flat dicts. Active-version switches are stored
# as a pseudo-field on the shot entity so the same before/after machinery works.
ACTIVE_FIELD_IMAGE = "active_image_asset_id"
ACTIVE_FIELD_VIDEO = "active_video_asset_id"
ACTIVE_FIELDS = (ACTIVE_FIELD_IMAGE, ACTIVE_FIELD_VIDEO)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ChangeSetService:
    """Owns the AgentChangeSet lifecycle: record → review → undo (compensate)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotService(session)
        self.versions = VersionService(session)

    # ---------- record ----------

    def record_shot_patch(
        self,
        *,
        project_id: str,
        run_id: str | None,
        tool: str,
        shot_id: str,
        before: dict,
        after: dict,
        revision_before: int,
        revision_after: int,
    ) -> AgentChangeSet:
        """Record one applied shot-patch mutation (after ShotService committed).

        before/after are minimal {field: value} dicts over the SAME field set —
        the fields the mutation actually changed.
        """
        if set(before) != set(after) or not before:
            raise ValidationError(
                "ChangeSet before/after must cover the same non-empty field set.",
                {"before_fields": sorted(before), "after_fields": sorted(after)},
            )
        change_set = AgentChangeSet(
            project_id=project_id,
            run_id=run_id,
            source="agent",
            tool=tool,
            entity_type="shot",
            entity_id=shot_id,
            revision_before=revision_before,
            revision_after=revision_after,
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(after, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(change_set)
        self.session.commit()
        self._publish_created(change_set)
        logger.info(
            "change_set %s recorded (run %s, shot %s, fields %s, rev %d→%d)",
            change_set.id, run_id, shot_id, sorted(before), revision_before, revision_after,
        )
        return change_set

    def record_scene_patch(
        self,
        *,
        project_id: str,
        run_id: str | None,
        tool: str,
        scene_id: str,
        before: dict,
        after: dict,
        revision_before: int,
        revision_after: int,
    ) -> AgentChangeSet:
        """Record one applied scene-patch mutation (自主迭代 07, update_scene).

        Same minimal before/after contract as shot patches; entity_type="scene"
        so the shared undo machinery compensates via SceneService (which re-triggers
        P8-T017 continuity recompute).
        """
        if set(before) != set(after) or not before:
            raise ValidationError(
                "ChangeSet before/after must cover the same non-empty field set.",
                {"before_fields": sorted(before), "after_fields": sorted(after)},
            )
        change_set = AgentChangeSet(
            project_id=project_id,
            run_id=run_id,
            source="agent",
            tool=tool,
            entity_type="scene",
            entity_id=scene_id,
            revision_before=revision_before,
            revision_after=revision_after,
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(after, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(change_set)
        self.session.commit()
        self._publish_created(change_set)
        logger.info(
            "change_set %s recorded (scene %s, tool %s, fields %s, rev %d→%d)",
            change_set.id, scene_id, tool, sorted(before), revision_before, revision_after,
        )
        return change_set

    def record_active_version(
        self,
        *,
        project_id: str,
        run_id: str | None,
        tool: str,
        shot_id: str,
        media_type: str,
        before_asset_id: str | None,
        after_asset_id: str | None,
        revision: int,
    ) -> AgentChangeSet:
        """Record an active-version pointer switch (media versions stay immutable;
        undo only flips the pointer back — nothing is deleted)."""
        field = ACTIVE_FIELD_IMAGE if media_type == "image" else ACTIVE_FIELD_VIDEO
        change_set = AgentChangeSet(
            project_id=project_id,
            run_id=run_id,
            source="agent",
            tool=tool,
            entity_type="shot",
            entity_id=shot_id,
            revision_before=revision,
            revision_after=revision,
            before_json=json.dumps({field: before_asset_id}, ensure_ascii=False),
            after_json=json.dumps({field: after_asset_id}, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(change_set)
        self.session.commit()
        self._publish_created(change_set)
        logger.info(
            "change_set %s recorded (active %s switch, shot %s, run %s)",
            change_set.id, media_type, shot_id, run_id,
        )
        return change_set

    def record_timeline_clip_patch(
        self,
        *,
        project_id: str,
        run_id: str | None,
        tool: str,
        clip_id: str,
        before: dict,
        after: dict,
        revision_before: int,
        revision_after: int,
    ) -> AgentChangeSet:
        """Record one applied user Timeline edit (P4-E3-T02 AC-2, source="timeline").

        Same minimal before/after contract as Agent mutations so the shared undo
        machinery can compensate it.
        """
        if set(before) != set(after) or not before:
            raise ValidationError(
                "ChangeSet before/after must cover the same non-empty field set.",
                {"before_fields": sorted(before), "after_fields": sorted(after)},
            )
        change_set = AgentChangeSet(
            project_id=project_id,
            run_id=run_id,
            source="timeline",
            tool=tool,
            entity_type="timeline_clip",
            entity_id=clip_id,
            revision_before=int(revision_before),
            revision_after=int(revision_after),
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(after, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(change_set)
        self.session.commit()
        self._publish_created(change_set)
        logger.info(
            "change_set %s recorded (timeline clip %s, tool %s, fields %s, rev %d→%d)",
            change_set.id, clip_id, tool, sorted(before), revision_before, revision_after,
        )
        return change_set

    # ---------- undo ----------

    def undo(self, change_set_id: str, *, force: bool = False) -> AgentChangeSet:
        """Undo one change set by applying the recorded before-values as a NEW
        compensating change. Returns the compensating change set.

        Conflict (409) with a recovery payload when a later edit overwrote the
        same fields — unless force=True (explicit recovery path).
        """
        original = self._get(change_set_id)
        if original.undone:
            raise ConflictError(
                "Change set already undone (undo is terminal/idempotent).",
                {"change_set_id": change_set_id, "undone_by": original.undone_by_change_set_id},
            )
        if original.source not in ("agent", "timeline"):
            raise ConflictError(
                "Only agent or timeline change sets can be undone.",
                {"change_set_id": change_set_id, "source": original.source},
            )
        before = json.loads(original.before_json) if original.before_json else {}
        after = json.loads(original.after_json) if original.after_json else {}

        if original.entity_type == "timeline_clip":
            return self._undo_timeline_clip(original, before, after, force=force)
        if original.entity_type == "scene":
            return self._undo_scene_patch(original, before, after, force=force)
        if any(f in ACTIVE_FIELDS for f in before):
            return self._undo_active_version(original, before, after, force=force)
        return self._undo_shot_patch(original, before, after, force=force)

    def _undo_shot_patch(self, original: AgentChangeSet, before: dict, after: dict, *, force: bool) -> AgentChangeSet:
        shot = self.session.get(Shot, original.entity_id)
        if shot is None or shot.deleted_at:
            raise ConflictError(
                "Target shot no longer exists — cannot undo.",
                {"change_set_id": original.id, "shot_id": original.entity_id, "recovery": before},
            )
        # Field-level guard: undo only what later edits did NOT overwrite.
        if not force:
            current = self._shot_field_values(shot, list(after))
            overwritten = {
                f: {"expected": after[f], "current": current[f], "before": before[f]}
                for f in after
                if current.get(f) != after[f]
            }
            if overwritten:
                raise ConflictError(
                    "Shot was edited after this change — undo would overwrite it. "
                    "Retry with force=true to restore the recorded before-values anyway.",
                    {"change_set_id": original.id, "fields": overwritten, "recovery": before},
                )
        patch = ShotUpdate.model_validate(before)
        revision_before = shot.revision
        updated = self.shots.update_shot(
            shot.id,
            shot.revision,
            patch,
            source="undo",
            run_id=original.run_id,
        )
        compensating = AgentChangeSet(
            project_id=original.project_id,
            run_id=original.run_id,
            source="undo",
            tool=f"undo:{original.tool}",
            entity_type="shot",
            entity_id=original.entity_id,
            revision_before=revision_before,
            revision_after=updated.revision,
            before_json=json.dumps(after, ensure_ascii=False),
            after_json=json.dumps(before, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(compensating)
        original.undone = True
        original.undone_at = _now()
        self.session.flush()  # assign compensating.id before linking
        original.undone_by_change_set_id = compensating.id
        self.session.commit()

        self._publish_created(compensating)
        self._publish_undone(original, compensating)
        logger.info("change_set %s undone by %s (shot %s, rev %d→%d)",
                    original.id, compensating.id, shot.id, revision_before, updated.revision)
        return compensating

    def _undo_scene_patch(self, original: AgentChangeSet, before: dict, after: dict, *, force: bool) -> AgentChangeSet:
        """Undo a scene patch (自主迭代 07): apply the recorded before-values as a
        NEW compensating change via SceneService (which re-triggers P8-T017)."""
        from app.domain.scene import SceneUpdate
        from app.services.scene_service import SceneService

        scene = self.session.get(Scene, original.entity_id)
        if scene is None or scene.deleted_at:
            raise ConflictError(
                "Target scene no longer exists — cannot undo.",
                {"change_set_id": original.id, "scene_id": original.entity_id, "recovery": before},
            )
        if not force:
            current = {f: getattr(scene, f, None) for f in after}
            overwritten = {
                f: {"expected": after[f], "current": current[f], "before": before[f]}
                for f in after
                if current.get(f) != after[f]
            }
            if overwritten:
                raise ConflictError(
                    "Scene was edited after this change — undo would overwrite it. "
                    "Retry with force=true to restore the recorded before-values anyway.",
                    {"change_set_id": original.id, "fields": overwritten, "recovery": before},
                )
        patch = SceneUpdate.model_validate(before)
        revision_before = scene.revision
        updated = SceneService(self.session).update_scene(scene.id, scene.revision, patch)
        compensating = AgentChangeSet(
            project_id=original.project_id,
            run_id=original.run_id,
            source="undo",
            tool=f"undo:{original.tool}",
            entity_type="scene",
            entity_id=original.entity_id,
            revision_before=revision_before,
            revision_after=updated.revision,
            before_json=json.dumps(after, ensure_ascii=False),
            after_json=json.dumps(before, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(compensating)
        original.undone = True
        original.undone_at = _now()
        self.session.flush()
        original.undone_by_change_set_id = compensating.id
        self.session.commit()

        self._publish_created(compensating)
        self._publish_undone(original, compensating)
        logger.info("change_set %s undone by %s (scene %s, rev %d→%d)",
                    original.id, compensating.id, scene.id, revision_before, updated.revision)
        return compensating

    def _undo_active_version(self, original: AgentChangeSet, before: dict, after: dict, *, force: bool) -> AgentChangeSet:
        field = next(f for f in before if f in ACTIVE_FIELDS)
        media_type = "image" if field == ACTIVE_FIELD_IMAGE else "video"
        shot = self.session.get(Shot, original.entity_id)
        if shot is None or shot.deleted_at:
            raise ConflictError(
                "Target shot no longer exists — cannot undo.",
                {"change_set_id": original.id, "shot_id": original.entity_id, "recovery": before},
            )
        current_asset = getattr(shot, f"active_{media_type}_asset_id")
        if not force and current_asset != after[field]:
            raise ConflictError(
                "Active version was switched after this change — undo would overwrite it. "
                "Retry with force=true to switch back anyway.",
                {
                    "change_set_id": original.id,
                    "fields": {field: {"expected": after[field], "current": current_asset, "before": before[field]}},
                    "recovery": before,
                },
            )
        restore_asset_id = before[field]
        if restore_asset_id is None:
            # The shot had NO active version before — clear the pointer.
            setattr(shot, f"active_{media_type}_asset_id", None)
        else:
            self.versions.set_active_asset(restore_asset_id)
        compensating = AgentChangeSet(
            project_id=original.project_id,
            run_id=original.run_id,
            source="undo",
            tool=f"undo:{original.tool}",
            entity_type="shot",
            entity_id=original.entity_id,
            revision_before=shot.revision,
            revision_after=shot.revision,
            before_json=json.dumps(after, ensure_ascii=False),
            after_json=json.dumps(before, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(compensating)
        original.undone = True
        original.undone_at = _now()
        self.session.flush()
        original.undone_by_change_set_id = compensating.id
        self.session.commit()

        if restore_asset_id is not None:
            # set_active_asset already published the switch; for the cleared
            # pointer case publish it here so the UI refreshes.
            pass
        else:
            bus.publish(StudioEvent(
                event_type=EVENT_SHOT_ACTIVE_VERSION_CHANGED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=original.project_id,
                payload={"media_type": media_type, "asset_id": None, "version_number": None},
            ))
        self._publish_created(compensating)
        self._publish_undone(original, compensating)
        logger.info("change_set %s undone by %s (active %s switch, shot %s)",
                    original.id, compensating.id, media_type, shot.id)
        return compensating

    def _undo_timeline_clip(self, original: AgentChangeSet, before: dict, after: dict, *, force: bool) -> AgentChangeSet:
        """Undo a user Timeline edit (P4-E3-T02 AC-2): apply the recorded
        before-values as a NEW compensating change through TimelineService."""
        from app.services.timeline_service import TimelineService

        clip = self.session.get(TimelineClip, original.entity_id)
        if clip is None:
            raise ConflictError(
                "Target timeline clip no longer exists — cannot undo.",
                {"change_set_id": original.id, "clip_id": original.entity_id, "recovery": before},
            )
        if not force:
            overwritten = {
                f: {"expected": after[f], "current": getattr(clip, f, None), "before": before[f]}
                for f in after
                if getattr(clip, f, None) != after[f]
            }
            if overwritten:
                raise ConflictError(
                    "Timeline clip was edited after this change — undo would overwrite it. "
                    "Retry with force=true to restore the recorded before-values anyway.",
                    {"change_set_id": original.id, "fields": overwritten, "recovery": before},
                )
        svc = TimelineService(self.session)
        rev_before = int(clip.revision or 1)
        if "asset_id" in before:
            svc.replace_clip_asset(clip.id, before["asset_id"], record_change_set=False)
        else:
            patch = TimelineClipUpdatePatch(**before, revision=clip.revision)
            svc.update_clip(clip.id, patch, run_id=original.run_id, record_change_set=False)
        compensating = AgentChangeSet(
            project_id=original.project_id,
            run_id=original.run_id,
            source="undo",
            tool=f"undo:{original.tool}",
            entity_type="timeline_clip",
            entity_id=original.entity_id,
            revision_before=rev_before,
            revision_after=rev_before + 1,
            before_json=json.dumps(after, ensure_ascii=False),
            after_json=json.dumps(before, ensure_ascii=False),
            created_at=_now(),
        )
        self.session.add(compensating)
        original.undone = True
        original.undone_at = _now()
        self.session.flush()
        original.undone_by_change_set_id = compensating.id
        self.session.commit()

        self._publish_created(compensating)
        self._publish_undone(original, compensating)
        logger.info("change_set %s undone by %s (timeline clip %s)",
                    original.id, compensating.id, original.entity_id)
        return compensating

    def undo_run(self, run_id: str, *, force: bool = False) -> list[dict]:
        """Undo all agent change sets of a run, newest first. Per-item results —
        never a half-silent batch: each item reports undone | conflict | skipped."""
        rows = list(
            self.session.scalars(
                select(AgentChangeSet)
                .where(AgentChangeSet.run_id == run_id, AgentChangeSet.source == "agent")
                .order_by(AgentChangeSet.created_at.desc(), AgentChangeSet.id.desc())
            )
        )
        results: list[dict] = []
        for row in rows:
            if row.undone:
                results.append({"id": row.id, "status": "skipped", "reason": "already undone"})
                continue
            try:
                compensating = self.undo(row.id, force=force)
                results.append({"id": row.id, "status": "undone", "compensating_change_set_id": compensating.id})
            except ConflictError as exc:
                results.append({"id": row.id, "status": "conflict", "reason": exc.message})
        return results

    # ---------- reads ----------

    def list_change_sets(
        self,
        project_id: str | None = None,
        run_id: str | None = None,
        entity_id: str | None = None,
        undone: bool | None = None,
        limit: int = 100,
    ) -> list[AgentChangeSet]:
        stmt = select(AgentChangeSet).order_by(AgentChangeSet.created_at.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(AgentChangeSet.project_id == project_id)
        if run_id:
            stmt = stmt.where(AgentChangeSet.run_id == run_id)
        if entity_id:
            stmt = stmt.where(AgentChangeSet.entity_id == entity_id)
        if undone is not None:
            stmt = stmt.where(AgentChangeSet.undone.is_(undone))
        return list(self.session.scalars(stmt))

    def get_change_set(self, change_set_id: str) -> AgentChangeSet:
        return self._get(change_set_id)

    # ---------- helpers ----------

    def _get(self, change_set_id: str) -> AgentChangeSet:
        change_set = self.session.get(AgentChangeSet, change_set_id)
        if change_set is None:
            raise NotFoundError("Change set does not exist.", {"change_set_id": change_set_id})
        return change_set

    def _shot_field_values(self, shot: Shot, fields: list[str]) -> dict:
        """Read the shot's user-visible values for the given fields (read DTO
        honors the ShotVisualSpec preference, P2-T005)."""
        read = self.shots.get_shot(shot.id)
        return {f: getattr(read, f, None) for f in fields}

    def _publish_created(self, change_set: AgentChangeSet) -> None:
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_CHANGE_SET_CREATED,
            entity_type="agent_change_set",
            entity_id=change_set.id,
            project_id=change_set.project_id,
            payload={
                "run_id": change_set.run_id,
                "source": change_set.source,
                "tool": change_set.tool,
                "entity_type": change_set.entity_type,
                "entity_id": change_set.entity_id,
                "revision_before": change_set.revision_before,
                "revision_after": change_set.revision_after,
                "before": json.loads(change_set.before_json) if change_set.before_json else {},
                "after": json.loads(change_set.after_json) if change_set.after_json else {},
            },
        ))

    def _publish_undone(self, original: AgentChangeSet, compensating: AgentChangeSet) -> None:
        bus.publish(StudioEvent(
            event_type=EVENT_AGENT_CHANGE_SET_UNDONE,
            entity_type="agent_change_set",
            entity_id=original.id,
            project_id=original.project_id,
            payload={
                "run_id": original.run_id,
                "compensating_change_set_id": compensating.id,
                "entity_id": original.entity_id,
            },
        ))


def to_read(cs: AgentChangeSet) -> ChangeSetRead:
    """ORM → DTO (api layer uses this to build responses)."""
    return ChangeSetRead(
        id=cs.id,
        project_id=cs.project_id,
        run_id=cs.run_id,
        source=cs.source,
        tool=cs.tool,
        entity_type=cs.entity_type,
        entity_id=cs.entity_id,
        revision_before=cs.revision_before,
        revision_after=cs.revision_after,
        before=json.loads(cs.before_json) if cs.before_json else {},
        after=json.loads(cs.after_json) if cs.after_json else {},
        undone=cs.undone,
        undone_at=cs.undone_at,
        undone_by_change_set_id=cs.undone_by_change_set_id,
        created_at=cs.created_at,
    )


def shot_project_id(session: Session, shot_id: str) -> str | None:
    """Resolve the owning project of a shot (change-set rows are project-scoped)."""
    shot = session.get(Shot, shot_id)
    if shot is None:
        return None
    scene = session.get(Scene, shot.scene_id)
    if scene is None:
        return None
    episode = session.get(Episode, scene.episode_id)
    return episode.project_id if episode else None
