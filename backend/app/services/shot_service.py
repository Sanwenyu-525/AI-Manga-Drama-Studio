"""ShotService — the core production service (backend-architecture §14, mvp-spec §26).

Rules:
- update_shot() increments revision (optimistic concurrency, api-event-contract §21/§88).
- All mutations publish domain events AFTER commit (red line: commit then publish).
- No provider/model knowledge here (red line: ShotService never knows concrete models).
- Character assignment lives in the shot_characters link table (database-v0.1 §11);
  character_ids are validated against the owning project (cross-project refs are rejected).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Character, Episode, Scene, Shot, ShotCharacter
from app.domain.scene import SceneSummary
from app.domain.shot import (
    ShotCreate,
    ShotRead,
    ShotSummary,
    ShotUpdate,
    StoryboardRead,
)
from app.events.bus import (
    EVENT_SHOT_CREATED,
    EVENT_SHOT_DELETED,
    EVENT_SHOT_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import SceneRepository, ShotCharacterRepository, ShotRepository

DIRTY_FIELDS = {
    "image_prompt",
    "negative_prompt",
    "shot_type",
    "camera_angle",
    "camera_movement",
    "lens",
    "action",
    "emotion",
    "duration",
    "character_ids",
}


def _to_read(s: Shot, character_ids: list[str] | None = None) -> ShotRead:
    return ShotRead(
        id=s.id,
        scene_id=s.scene_id,
        shot_number=s.shot_number,
        shot_order=s.shot_order,
        shot_type=s.shot_type,
        camera_angle=s.camera_angle,
        camera_movement=s.camera_movement,
        lens=s.lens,
        duration=s.duration,
        action=s.action,
        emotion=s.emotion,
        dialogue=s.dialogue,
        image_prompt=s.image_prompt,
        character_ids=character_ids or [],
        status=s.status,
        dirty_state=s.dirty_state,
        revision=s.revision,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_summary(s: Shot, character_names: list[str] | None = None) -> ShotSummary:
    return ShotSummary(
        id=s.id,
        shot_number=s.shot_number,
        shot_type=s.shot_type,
        duration=s.duration,
        status=s.status,
        dirty_state=s.dirty_state,
        thumbnail_url=None,  # resolved per-shot in get_storyboard (needs DB lookups)
        character_names=character_names or [],
    )


class ShotService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ShotRepository(session)
        self.scenes = SceneRepository(session)
        self.links = ShotCharacterRepository(session)

    def create_shot(self, scene_id: str, data: ShotCreate) -> ShotRead:
        """Create ONE shot; commits and publishes shot.created (manual/API path)."""
        shot = self.create_shots(scene_id, [data])[0]
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_CREATED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=self._project_id_of(shot),
            )
        )
        return _to_read(shot, data.character_ids)

    def create_shots(
        self,
        scene_id: str,
        datas: list[ShotCreate],
        analysis_key: str | None = None,
    ) -> list[Shot]:
        """Batch create WITHOUT committing (P1-E1-T01: caller owns the transaction).

        All-or-nothing: any error raises before commit; the caller rolls back and
        nothing is persisted. analysis_key marks AI-created shots (replace policy).
        """
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        created: list[Shot] = []
        for data in datas:
            shot_number = data.shot_number or self.repo.next_shot_number(scene_id)
            shot = Shot(
                scene_id=scene_id,
                shot_number=shot_number,
                shot_order=shot_number,
                shot_type=data.shot_type,
                camera_angle=data.camera_angle,
                camera_movement=data.camera_movement,
                lens=data.lens,
                duration=data.duration,
                action=data.action,
                emotion=data.emotion,
                dialogue=data.dialogue,
                image_prompt=data.image_prompt,
                analysis_key=analysis_key,
                status="draft",
                dirty_state="clean",
                revision=1,
            )
            self.repo.add(shot)
            self.session.flush()  # assign shot.id before link rows reference it (autoflush=False)
            if data.character_ids:
                self._validate_characters(data.character_ids, scene)
                self._replace_characters(shot, data.character_ids)
            created.append(shot)
        return created

    def soft_delete_shots(self, scene_ids: list[str]) -> None:
        """Soft-delete ALL live shots of the given scenes (no commit — caller owns the transaction)."""
        if not scene_ids:
            return
        shots = self.session.scalars(
            select(Shot).where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
        )
        for shot in shots:
            self.repo.delete(shot)

    def soft_delete_ai_shots(self, scene_id: str) -> None:
        """Soft-delete AI-created shots of one scene (analysis_key IS NOT NULL);
        manual shots are preserved. No commit — caller owns the transaction."""
        shots = self.session.scalars(
            select(Shot).where(
                Shot.scene_id == scene_id,
                Shot.analysis_key.isnot(None),
                Shot.deleted_at.is_(None),
            )
        )
        for shot in shots:
            self.repo.delete(shot)

    def list_shots_with_key(self, scene_id: str, analysis_key: str) -> list[Shot]:
        """Live shots of a scene created by a specific storyboard key (idempotency check)."""
        return self.repo.list_ordered(
            order_by="shot_order", scene_id=scene_id, analysis_key=analysis_key
        )

    def get_shot(self, shot_id: str) -> ShotRead:
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        ids, _ = self._character_data([shot_id])
        return _to_read(shot, ids.get(shot_id, []))

    def list_shots(self, scene_id: str) -> list[ShotRead]:
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        shots = self.repo.list_for_scene(scene_id)
        ids, _ = self._character_data([s.id for s in shots])
        return [_to_read(s, ids.get(s.id, [])) for s in shots]

    def update_shot(
        self,
        shot_id: str,
        revision: int,
        patch: ShotUpdate,
        source: str = "user",
        run_id: str | None = None,
    ) -> ShotRead:
        """Optimistic concurrency update: revision must match; every mutation bumps revision.

        P1-E3-T02: source ("user" | "agent") and run_id are recorded in the
        shot.updated event payload so the audit trail can distinguish origins.
        """
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        if shot.revision != revision:
            raise ConflictError(
                "Shot was modified by another writer.",
                {"shot_id": shot_id, "expected_revision": revision, "current_revision": shot.revision},
            )
        changed: list[str] = []
        for field in (
            "shot_type",
            "camera_angle",
            "camera_movement",
            "lens",
            "duration",
            "action",
            "emotion",
            "dialogue",
            "image_prompt",
            "status",
            "dirty_state",
        ):
            value = getattr(patch, field)
            if value is not None:
                setattr(shot, field, value)
                changed.append(field)
        if patch.character_ids is not None:
            scene = self.session.get(Scene, shot.scene_id)
            self._validate_characters(patch.character_ids, scene)
            self._replace_characters(shot, patch.character_ids)
            changed.append("character_ids")
        if changed:
            shot.revision += 1
            if any(f in DIRTY_FIELDS for f in changed):
                shot.dirty_state = "dirty_image"
        self.session.commit()
        if changed:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_SHOT_UPDATED,
                    entity_type="shot",
                    entity_id=shot.id,
                    project_id=self._project_id_of(shot),
                    payload={
                        "revision": shot.revision,
                        "changed_fields": changed,
                        "source": source,
                        "run_id": run_id,
                    },
                )
            )
        ids, _ = self._character_data([shot_id])
        return _to_read(shot, ids.get(shot_id, []))

    def delete_shot(self, shot_id: str) -> None:
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        self.repo.delete(shot)  # soft delete
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_DELETED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=self._project_id_of(shot),
            )
        )

    def reorder_shots(self, scene_id: str, ordered_ids: list[str]) -> list[ShotRead]:
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        shots = {s.id: s for s in self.repo.list_for_scene(scene_id)}
        unknown = [sid for sid in ordered_ids if sid not in shots]
        if unknown:
            raise NotFoundError("Shot does not exist.", {"shot_ids": unknown})
        for index, shot_id in enumerate(ordered_ids, start=1):
            shot = shots[shot_id]
            shot.shot_order = index
            shot.shot_number = index
        self.session.commit()
        ids, _ = self._character_data(list(shots))
        return [_to_read(s, ids.get(s.id, [])) for s in self.repo.list_for_scene(scene_id)]

    def get_storyboard(self, scene_id: str) -> StoryboardRead:
        """Aggregate endpoint payload (api-event-contract §101-102) — avoids N+1 on the grid."""
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        episode = self.session.get(Episode, scene.episode_id)
        shots = self.repo.list_for_scene(scene_id)
        thumbnails = self._thumbnail_urls(shots)
        _, names = self._character_data([s.id for s in shots])
        summaries = []
        for s in shots:
            summary = _to_summary(s, names.get(s.id, []))
            summary.thumbnail_url = thumbnails.get(s.id)
            summaries.append(summary)
        return StoryboardRead(
            scene=SceneSummary(id=scene.id, scene_number=scene.scene_number, name=scene.name),
            shots=summaries,
        )

    # --- character assignment (database-v0.1 §11) ---

    def _validate_characters(self, character_ids: list[str], scene: Scene | None) -> None:
        """Characters must exist (not deleted) and belong to the shot's project."""
        from app.core.errors import ValidationError

        if not character_ids:
            return
        characters = {
            c.id: c
            for c in self.session.scalars(
                select(Character).where(Character.id.in_(character_ids))
            )
        }
        unknown = [cid for cid in character_ids if cid not in characters]
        if unknown:
            raise NotFoundError("Character does not exist.", {"character_ids": unknown})
        project_id = self._project_id_of(scene) if scene else None
        foreign = [cid for cid in character_ids if characters[cid].project_id != project_id]
        if foreign:
            raise ValidationError(
                "Character belongs to another project.",
                {"character_ids": foreign, "project_id": project_id},
            )

    def _replace_characters(self, shot: Shot, character_ids: list[str]) -> None:
        """Replace the shot's character links (ephemeral link rows, no version history)."""
        self.links.delete_for_shot(shot.id)
        for character_id in character_ids:
            self.session.add(ShotCharacter(shot_id=shot.id, character_id=character_id))

    def _character_data(self, shot_ids: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """(shot_id → character_ids, shot_id → character_names) — soft-deleted characters
        keep their name as history; links are ordered by insertion."""
        if not shot_ids:
            return {}, {}
        links = self.links.list_for_shots(shot_ids)
        if not links:
            return {}, {}
        character_ids = {l.character_id for l in links}
        characters = {
            c.id: c.name
            for c in self.session.scalars(select(Character).where(Character.id.in_(character_ids)))
        }
        ids_map: dict[str, list[str]] = {}
        names_map: dict[str, list[str]] = {}
        for link in links:
            ids_map.setdefault(link.shot_id, []).append(link.character_id)
            names_map.setdefault(link.shot_id, []).append(
                characters.get(link.character_id, link.character_id)
            )
        return ids_map, names_map

    def _thumbnail_urls(self, shots: list[Shot]) -> dict[str, str | None]:
        """Map shot_id → thumbnail URL via the shot's active image version (Stage C)."""
        from app.db.models import Asset, MediaVersion

        version_ids = [s.active_image_version_id for s in shots if s.active_image_version_id]
        if not version_ids:
            return {s.id: None for s in shots}
        versions = {
            v.id: v
            for v in self.session.scalars(
                select(MediaVersion).where(MediaVersion.id.in_(version_ids))
            )
        }
        asset_ids = [v.asset_id for v in versions.values()]
        assets = {
            a.id: a
            for a in self.session.scalars(select(Asset).where(Asset.id.in_(asset_ids)))
        }
        return {
            s.id: (f"/api/v1/assets/{versions[s.active_image_version_id].asset_id}/thumbnail"
                   if s.active_image_version_id in versions else None)
            for s in shots
        }

    def _project_id_of(self, obj: Shot | Scene) -> str | None:
        if isinstance(obj, Shot):
            scene = self.session.get(Scene, obj.scene_id)
        else:
            scene = obj
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
