"""Continuity state repositories (P8-T001/T003)."""

from sqlalchemy import select

from app.db.models import SceneContinuityState, ShotContinuityState
from app.repositories.base import SQLAlchemyRepository


class SceneContinuityRepository(SQLAlchemyRepository[SceneContinuityState]):
    """Scene-continuity rows are keyed by scene_id (no soft delete, no created_at ordering)."""

    model = SceneContinuityState

    def get_by_scene(self, scene_id: str) -> SceneContinuityState | None:
        stmt = select(SceneContinuityState).where(SceneContinuityState.scene_id == scene_id)
        return self.session.scalars(stmt).first()


class ShotContinuityRepository(SQLAlchemyRepository[ShotContinuityState]):
    """Shot-continuity rows are keyed by shot_id (no soft delete)."""

    model = ShotContinuityState

    def get_by_shot(self, shot_id: str) -> ShotContinuityState | None:
        stmt = select(ShotContinuityState).where(ShotContinuityState.shot_id == shot_id)
        return self.session.scalars(stmt).first()

    def list_by_scene(self, scene_id: str) -> list[ShotContinuityState]:
        stmt = select(ShotContinuityState).where(ShotContinuityState.scene_id == scene_id)
        return list(self.session.scalars(stmt))
