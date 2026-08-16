"""SceneService (backend-architecture §13, mvp-spec §25)."""

import re
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Episode, Scene, Shot
from app.domain.scene import SceneCreate, SceneRead, SceneUpdate
from app.events.bus import EVENT_SCENE_CREATED, EVENT_SCENE_DELETED, EVENT_SCENE_UPDATED, StudioEvent, bus
from app.repositories import EpisodeRepository, SceneRepository

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_uuid(value: str) -> bool:
    """True when value is a canonical UUID hex form (a real Location reference),
    False for legacy free-text location names like "体育馆" / "L1"."""
    return bool(_UUID_RE.match(value or ""))

SCENE_UPDATE_FIELDS = (
    "name",
    "location_id",
    "time_of_day",
    "lighting",
    "weather",
    "mood",
    "description",
    "status",
)


def _to_read(scene: Scene, shot_count: int = 0) -> SceneRead:
    return SceneRead(
        id=scene.id,
        scene_number=scene.scene_number,
        name=scene.name,
        episode_id=scene.episode_id,
        location_id=scene.location_id,
        time_of_day=scene.time_of_day,
        lighting=scene.lighting,
        weather=scene.weather,
        mood=scene.mood,
        description=scene.description,
        scene_order=scene.scene_order,
        status=scene.status,
        shot_count=shot_count,
        revision=scene.revision,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


class SceneService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SceneRepository(session)
        self.episodes = EpisodeRepository(session)

    def create_scene(self, episode_id: str, data: SceneCreate) -> SceneRead:
        """Create ONE scene; commits and publishes scene.created (manual/API path)."""
        scene = self.create_scenes(episode_id, [data])[0]
        self.session.commit()
        episode = self.episodes.get(episode_id)
        bus.publish(
            StudioEvent(
                event_type=EVENT_SCENE_CREATED,
                entity_type="scene",
                entity_id=scene.id,
                project_id=episode.project_id if episode else None,
            )
        )
        return _to_read(scene)

    def create_scenes(
        self,
        episode_id: str,
        datas: list[SceneCreate],
        analysis_key: str | None = None,
    ) -> list[Scene]:
        """Batch create WITHOUT committing (P1-E1-T01: caller owns the transaction).

        All-or-nothing: any error raises before commit; the caller rolls back and
        nothing is persisted. analysis_key marks AI-created scenes (replace policy).
        """
        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        created: list[Scene] = []
        for data in datas:
            # P2-T009: validate a Location UUID reference on scenes.location_id — legacy
            # free-text passes through; real references are checked for existence + project.
            if data.location_id is not None:
                self._validate_location(data.location_id, episode.project_id)
            scene_number = data.scene_number or self.repo.next_scene_number(episode_id)
            scene = Scene(
                episode_id=episode_id,
                scene_number=scene_number,
                scene_order=scene_number,
                name=data.name,
                location_id=data.location_id,
                time_of_day=data.time_of_day,
                lighting=data.lighting,
                weather=data.weather,
                mood=data.mood,
                description=data.description,
                analysis_key=analysis_key,
                status="draft",
                revision=1,
            )
            self.repo.add(scene)
            created.append(scene)
        return created

    def soft_delete_scenes(self, scene_ids: list[str]) -> None:
        """Soft-delete scenes WITHOUT committing (P1-E1-T01: caller owns the transaction)."""
        if not scene_ids:
            return
        scenes = self.session.scalars(
            select(Scene).where(Scene.id.in_(scene_ids), Scene.deleted_at.is_(None))
        )
        for scene in scenes:
            self.repo.delete(scene)

    def get_scene(self, scene_id: str) -> SceneRead:
        scene = self.repo.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        return _to_read(scene, shot_count=self._count_shots(scene_id))

    def list_scenes(self, episode_id: str) -> list[SceneRead]:
        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        scenes = self.repo.list_ordered(order_by="scene_number", episode_id=episode_id)
        counts = self._shot_counts([s.id for s in scenes])
        return [_to_read(s, counts.get(s.id, 0)) for s in scenes]

    def update_scene(self, scene_id: str, revision: int, patch: SceneUpdate) -> SceneRead:
        """Optimistic concurrency (AGENTS.md §3.10): atomic conditional UPDATE.

        UPDATE scenes SET revision = revision + 1 WHERE id = ? AND revision = ?
        """
        scene = self.repo.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        episode = self.episodes.get(scene.episode_id)
        project_id = episode.project_id if episode else None

        values: dict = {}
        changed: list[str] = []
        for field in SCENE_UPDATE_FIELDS:
            value = getattr(patch, field)
            if value is not None:
                values[field] = value
                changed.append(field)
        # P2-T009: weak location ref validated service-side (existence + project).
        if patch.location_id is not None and project_id is not None:
            self._validate_location(patch.location_id, project_id)
        if not changed:
            return _to_read(scene, shot_count=self._count_shots(scene_id))

        values["updated_at"] = datetime.now(UTC).isoformat()
        stmt = (
            update(Scene)
            .where(
                Scene.id == scene_id,
                Scene.revision == revision,
                Scene.deleted_at.is_(None),
            )
            .values(revision=Scene.revision + 1, **values)
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            current = self.session.scalar(
                select(Scene.revision).where(Scene.id == scene_id)
            )
            raise ConflictError(
                "Scene was modified by another writer.",
                {
                    "scene_id": scene_id,
                    "expected_revision": revision,
                    "current_revision": current,
                },
            )
        self.session.commit()
        self.session.refresh(scene)
        bus.publish(
            StudioEvent(
                event_type=EVENT_SCENE_UPDATED,
                entity_type="scene",
                entity_id=scene.id,
                project_id=project_id,
                payload={"revision": scene.revision, "changed_fields": changed},
            )
        )
        # P8-T017: a scene base edit recomputes the scene base + all shots and marks
        # their active assets STALE (no regen).
        self._recompute_continuity(scene.id)
        return _to_read(scene, shot_count=self._count_shots(scene_id))

    def _recompute_continuity(self, scene_id: str) -> None:
        """P8-T017 hook — best-effort; a continuity failure never breaks the scene edit."""
        try:
            from app.services.continuity_service import ContinuityService

            ContinuityService(self.session).recompute_after_scene_change(scene_id)
        except Exception:
            from app.core.logging import get_logger

            get_logger("continuity").exception(
                "continuity recompute failed after scene change", scene_id=scene_id
            )

    def delete_scene(self, scene_id: str) -> None:
        scene = self.repo.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        self.repo.delete(scene)  # soft delete
        self.session.commit()
        episode = self.session.get(Episode, scene.episode_id)
        bus.publish(
            StudioEvent(
                event_type=EVENT_SCENE_DELETED,
                entity_type="scene",
                entity_id=scene.id,
                project_id=episode.project_id if episode else None,
            )
        )

    def _validate_location(self, location_id: str, project_id: str | None) -> None:
        """P2-T009: validate a Location REFERENCE on scenes.location_id.

        scenes.location_id is a weak Text ref, so legacy free-text values (e.g. "体育馆",
        "L1") must keep working untouched. Validation only kicks in when the value looks
        like a real Location UUID (the new reference form): then it must exist (404) and
        belong to the same project (422)."""

        # legacy free-text location — not a UUID reference; pass through unvalidated
        if not _looks_like_uuid(location_id):
            return
        if project_id is None:
            raise NotFoundError("Location does not exist.", {"location_id": location_id})
        from app.core.errors import NotFoundError as NF  # shadowing safe
        from app.core.errors import ValidationError
        from app.db.models import Location

        location = self.session.scalar(
            select(Location).where(Location.id == location_id, Location.deleted_at.is_(None))
        )
        if location is None:
            raise NF("Location does not exist.", {"location_id": location_id})
        if location.project_id != project_id:
            raise ValidationError(
                "Location belongs to another project.",
                {"location_id": location_id, "project_id": project_id, "location_project_id": location.project_id},
            )

    def _count_shots(self, scene_id: str) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None))
        ) or 0

    def _shot_counts(self, scene_ids: list[str]) -> dict[str, int]:
        if not scene_ids:
            return {}
        rows = self.session.execute(
            select(Shot.scene_id, func.count())
            .where(Shot.scene_id.in_(scene_ids), Shot.deleted_at.is_(None))
            .group_by(Shot.scene_id)
        ).all()
        return {scene_id: count for scene_id, count in rows}
