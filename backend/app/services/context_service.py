"""ContextService (agent-director §26-27): Minimum Sufficient Context for the Director.

Only loads what the task needs (shot + scene + neighbors + generation status) —
never the whole project (context engineering principle).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Episode, Generation, Scene, Shot


class ContextService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_shot_context(self, shot_id: str) -> dict:
        shot = self.session.get(Shot, shot_id)
        if shot is None or shot.deleted_at:
            raise NotFoundError("Shot does not exist.", {"shot_id": shot_id})
        scene = self.session.get(Scene, shot.scene_id)
        episode = self.session.get(Episode, scene.episode_id) if scene else None

        neighbors: dict = {"previous": None, "next": None}
        if scene:
            shots = list(
                self.session.scalars(
                    select(Shot)
                    .where(Shot.scene_id == scene.id, Shot.deleted_at.is_(None))
                    .order_by(Shot.shot_order)
                )
            )
            for idx, s in enumerate(shots):
                if s.id == shot.id:
                    neighbors["previous"] = self._shot_brief(shots[idx - 1]) if idx > 0 else None
                    neighbors["next"] = self._shot_brief(shots[idx + 1]) if idx < len(shots) - 1 else None
                    break

        generation_status: list[dict] = []
        generations = list(
            self.session.scalars(
                select(Generation)
                .where(Generation.shot_id == shot.id, Generation.deleted_at.is_(None))
                .order_by(Generation.created_at.desc())
                .limit(3)
            )
        )
        for g in generations:
            generation_status.append(
                {"id": g.id, "type": g.type, "provider": g.provider, "status": g.status, "progress": g.progress}
            )

        return {
            "shot": self._shot_brief(shot),
            "scene": {"id": scene.id, "scene_number": scene.scene_number, "name": scene.name} if scene else None,
            "episode": {"id": episode.id, "episode_number": episode.episode_number, "title": episode.title} if episode else None,
            "neighbors": neighbors,
            "recent_generations": generation_status,
        }

    def resolve_shot_reference(self, project_id: str, reference: str | None, shot_ids: list[str]) -> str | None:
        """Resolve 'shot_number:5' or a raw shot id; falls back to selection (explicit > selection, contract §80)."""
        if not reference:
            return shot_ids[0] if shot_ids else None
        if reference.startswith("shot_number:"):
            number = int(reference.split(":", 1)[1])
            shot = self.session.scalar(
                select(Shot)
                .join(Scene)
                .join(Episode)
                .where(Episode.project_id == project_id, Shot.shot_number == number, Shot.deleted_at.is_(None))
                .order_by(Shot.created_at)
                .limit(1)
            )
            return shot.id if shot else None
        if self.session.get(Shot, reference) is not None:
            return reference
        return shot_ids[0] if shot_ids else None

    @staticmethod
    def _shot_brief(shot: Shot) -> dict:
        return {
            "id": shot.id,
            "shot_number": shot.shot_number,
            "shot_type": shot.shot_type,
            "camera_angle": shot.camera_angle,
            "camera_movement": shot.camera_movement,
            "duration": shot.duration,
            "action": shot.action,
            "emotion": shot.emotion,
            "image_prompt": shot.image_prompt,
            "status": shot.status,
            "dirty_state": shot.dirty_state,
            "revision": shot.revision,
        }
