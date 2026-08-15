"""ContextService (agent-director §26-27): Minimum Sufficient Context for the Director.

Only loads what the task needs (shot + scene + neighbors + generation status) —
never the whole project (context engineering principle).

P1-E3-T01 (强制 Agent Project Ownership 与 Run-local Context):

- resolve_shot_reference 校验存在性（含软删除）与 project ownership：跨项目 Shot ID、
  已删除 Shot、伪造 selection 一律返回 rejected/not_found，绝不静默回落。
- shot_number:N 先用 selection.scene_id 定域；项目内重号且无定域时返回 ambiguous
  （要求澄清），不再取首个。
- 返回结构化 ShotResolution，由 Graph 决定澄清/执行。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Episode, Generation, Scene, Shot

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"
REJECTED = "rejected"
NONE = "none"


@dataclass
class ShotResolution:
    """Outcome of reference resolution (P1-E3-T01): never guess, report status."""

    status: str = NONE  # resolved | ambiguous | not_found | rejected | none
    shot_id: str | None = None
    message: str | None = None


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

    def resolve_shot_reference(
        self,
        project_id: str,
        reference: str | None,
        shot_ids: list[str],
        scene_id: str | None = None,
    ) -> ShotResolution:
        """Resolve 'shot_number:N' or a raw shot id; falls back to selection.

        Rules (P1-E3-T01):
        - explicit reference wins over selection (contract §80);
        - every candidate shot must be live and owned by project_id;
        - shot_number:N is scoped to the selected scene first; project-wide matches
          must be unique, otherwise AMBIGUOUS (clarification required, no guessing);
        - forged/deleted selection → rejected/not_found, never silent fallback.
        """
        if reference:
            if reference.startswith("shot_number:"):
                try:
                    number = int(reference.split(":", 1)[1])
                except ValueError:
                    return ShotResolution(status=NOT_FOUND, message="镜头编号无效。")
                return self._resolve_by_number(project_id, number, scene_id)
            return self._resolve_raw_id(project_id, reference)
        if shot_ids:
            return self._resolve_raw_id(project_id, shot_ids[0])
        return ShotResolution(status=NONE, message="请先选中一个镜头，或说明要修改第几镜。")

    # --- resolution helpers ---

    def _resolve_raw_id(self, project_id: str, shot_id: str) -> ShotResolution:
        """Raw shot id: must exist, be live, and belong to the project (P1-E3-T01)."""
        shot = self.session.get(Shot, shot_id)
        if shot is None or shot.deleted_at:
            return ShotResolution(status=NOT_FOUND, message="镜头不存在或已删除。")
        if not self._shot_in_project(shot, project_id):
            return ShotResolution(
                status=REJECTED,
                message="镜头不属于当前项目。",
            )
        return ShotResolution(status=RESOLVED, shot_id=shot.id)

    def _resolve_by_number(self, project_id: str, number: int, scene_id: str | None) -> ShotResolution:
        """shot_number:N — scoped to the selected scene, else project-unique."""
        if scene_id:
            in_scene = self._shots_by_number(project_id, number, scene_id)
            if len(in_scene) == 1:
                return ShotResolution(status=RESOLVED, shot_id=in_scene[0].id)
            if len(in_scene) > 1:
                return ShotResolution(status=AMBIGUOUS, message="所选场景内存在多个同号镜头，请明确目标。")
        project_wide = self._shots_by_number(project_id, number)
        if len(project_wide) == 1:
            return ShotResolution(status=RESOLVED, shot_id=project_wide[0].id)
        if len(project_wide) > 1:
            return ShotResolution(
                status=AMBIGUOUS,
                message="项目中有多个同号镜头，请先选中目标场景再试。",
            )
        return ShotResolution(status=NOT_FOUND, message=f"未找到第 {number} 镜。")

    def _shots_by_number(self, project_id: str, number: int, scene_id: str | None = None) -> list[Shot]:
        stmt = (
            select(Shot)
            .join(Scene)
            .join(Episode)
            .where(
                Episode.project_id == project_id,
                Shot.shot_number == number,
                Shot.deleted_at.is_(None),
            )
        )
        if scene_id:
            stmt = stmt.where(Shot.scene_id == scene_id)
        return list(self.session.scalars(stmt.order_by(Shot.shot_order)))

    def _shot_in_project(self, shot: Shot, project_id: str) -> bool:
        """Shot's owning project (scene → episode → project_id) must match (P1-E3-T01)."""
        scene = self.session.get(Scene, shot.scene_id)
        if scene is None or scene.deleted_at:
            return False
        episode = self.session.get(Episode, scene.episode_id)
        return bool(episode and episode.project_id == project_id)

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
