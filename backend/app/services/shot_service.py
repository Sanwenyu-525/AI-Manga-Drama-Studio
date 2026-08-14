"""ShotService — the core production service (backend-architecture §14, mvp-spec §26).

Rules:
- update_shot() increments revision (optimistic concurrency, api-event-contract §21/§88).
- All mutations publish domain events AFTER commit (red line: commit then publish).
- No provider/model knowledge here (red line: ShotService never knows concrete models).
"""

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Episode, Scene, Shot
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
from app.repositories import SceneRepository, ShotRepository

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
}


def _to_read(s: Shot) -> ShotRead:
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
        status=s.status,
        dirty_state=s.dirty_state,
        revision=s.revision,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_summary(s: Shot) -> ShotSummary:
    return ShotSummary(
        id=s.id,
        shot_number=s.shot_number,
        shot_type=s.shot_type,
        duration=s.duration,
        status=s.status,
        dirty_state=s.dirty_state,
        thumbnail_url=None,  # populated once assets exist (Stage C)
    )


class ShotService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ShotRepository(session)
        self.scenes = SceneRepository(session)

    def create_shot(self, scene_id: str, data: ShotCreate) -> ShotRead:
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
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
            status="draft",
            dirty_state="clean",
            revision=1,
        )
        self.repo.add(shot)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_SHOT_CREATED,
                entity_type="shot",
                entity_id=shot.id,
                project_id=self._project_id_of(scene),
            )
        )
        return _to_read(shot)

    def get_shot(self, shot_id: str) -> ShotRead:
        shot = self.repo.get(shot_id)
        if shot is None:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        return _to_read(shot)

    def list_shots(self, scene_id: str) -> list[ShotRead]:
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        return [_to_read(s) for s in self.repo.list_for_scene(scene_id)]

    def update_shot(self, shot_id: str, revision: int, patch: ShotUpdate) -> ShotRead:
        """Optimistic concurrency update: revision must match; every mutation bumps revision."""
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
                    payload={"revision": shot.revision, "changed_fields": changed, "source": "user"},
                )
            )
        return _to_read(shot)

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
        return [_to_read(s) for s in self.repo.list_for_scene(scene_id)]

    def get_storyboard(self, scene_id: str) -> StoryboardRead:
        """Aggregate endpoint payload (api-event-contract §101-102) — avoids N+1 on the grid."""
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        episode = self.session.get(Episode, scene.episode_id)
        shots = self.repo.list_for_scene(scene_id)
        return StoryboardRead(
            scene=SceneSummary(id=scene.id, scene_number=scene.scene_number, name=scene.name),
            shots=[_to_summary(s) for s in shots],
        )

    def _project_id_of(self, obj: Shot | Scene) -> str | None:
        if isinstance(obj, Shot):
            scene = self.session.get(Scene, obj.scene_id)
        else:
            scene = obj
        if scene is None:
            return None
        episode = self.session.get(Episode, scene.episode_id)
        return episode.project_id if episode else None
