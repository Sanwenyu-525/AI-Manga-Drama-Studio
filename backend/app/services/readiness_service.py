"""ProjectReadinessService — 生产就绪度聚合（自主迭代 04，契约 §103.1）。

确定性规则聚合（无 LLM），回答「这部作品还差什么」：
- 角色 MASTER 覆盖：无 master_version_id 的角色无法注入参考图 → 一致性缺口。
- 场景地点绑定覆盖：场景绑定地点且该地点有 MASTER 时，生成才注入地点参考图。
- 开放连续性警告：continuity_warnings(status=open) 计数。

红线：Router 薄委派（api/projects.py）；只读聚合不写库；Project State 唯一可信。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Character, ContinuityWarning, Episode, Location, Scene
from app.domain.readiness import ReadinessMetric, ReadinessRead, SceneBindingReadiness


class ProjectReadinessService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def readiness(self, project_id: str) -> ReadinessRead:
        self._require_project(project_id)

        # --- 角色 MASTER 覆盖 ---
        char_total = self.session.scalar(
            select(func.count(Character.id)).where(
                Character.project_id == project_id,
                Character.deleted_at.is_(None),
            )
        ) or 0
        char_with_master = self.session.scalar(
            select(func.count(Character.id)).where(
                Character.project_id == project_id,
                Character.deleted_at.is_(None),
                Character.master_version_id.isnot(None),
            )
        ) or 0

        # --- 场景地点绑定覆盖 ---
        scenes = self.session.scalars(
            select(Scene)
            .join(Episode, Episode.id == Scene.episode_id)
            .where(Episode.project_id == project_id, Scene.deleted_at.is_(None))
        ).all()
        # 该项目的全部地点 → master 指针（一次查询，避免逐场景 N+1）
        master_by_location = {
            loc.id: loc.master_version_id
            for loc in self.session.scalars(
                select(Location).where(
                    Location.project_id == project_id,
                    Location.deleted_at.is_(None),
                )
            )
        }
        scenes_total = len(scenes)
        bound = 0
        bound_with_master = 0
        for scene in scenes:
            if scene.location_id:
                bound += 1
                if master_by_location.get(scene.location_id):
                    bound_with_master += 1

        # --- 开放连续性警告 ---
        continuity_open = self.session.scalar(
            select(func.count(ContinuityWarning.id)).where(
                ContinuityWarning.project_id == project_id,
                ContinuityWarning.status == "open",
            )
        ) or 0

        return ReadinessRead(
            characters=ReadinessMetric(
                total=char_total,
                ready=char_with_master,
                missing=char_total - char_with_master,
            ),
            scene_binding=SceneBindingReadiness(
                scenes_total=scenes_total,
                bound=bound,
                bound_with_master=bound_with_master,
                unbound=scenes_total - bound,
            ),
            continuity_open=continuity_open,
        )

    def _require_project(self, project_id: str) -> None:
        from app.db.models import Project

        project = self.session.get(Project, project_id)
        if project is None or project.deleted_at:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
