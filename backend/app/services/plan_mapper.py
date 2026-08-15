"""Explicit Plan ↔ Domain mapper (P1-E1-T01).

The LLM plan schemas (app.domain.analysis) and the Studio domain DTOs use
different field names (ScenePlan.title → SceneCreate.name, ScenePlan.location →
SceneCreate.location_id, ScenePlan.time → SceneCreate.time_of_day). A single
explicit mapper guarantees no field is silently dropped when AI plans become
Project State (red line: analysis results are the source of truth once persisted).

The reverse mappers replay persisted ORM rows back to plans so idempotent
re-submissions return the same contract payload without re-running the LLM.
The DB row must round-trip exactly — covered by tests.

No generic mapping framework: every field is listed explicitly on purpose.
"""

from __future__ import annotations

from app.db.models import Scene, Shot
from app.domain.analysis import ScenePlan, ShotPlan
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate


def scene_plan_to_create(plan: ScenePlan) -> SceneCreate:
    """ScenePlan → SceneCreate, field by field (no silent drops)."""
    return SceneCreate(
        scene_number=plan.scene_number,
        name=plan.title,
        location_id=plan.location,
        time_of_day=plan.time,
        description=plan.description,
        mood=plan.mood,
    )


def scene_to_plan(scene: Scene) -> ScenePlan:
    """Persisted Scene → ScenePlan (idempotent replay of a confirmed analysis)."""
    return ScenePlan(
        scene_number=scene.scene_number,
        title=scene.name or "",
        location=scene.location_id or "",
        time=scene.time_of_day,
        description=scene.description or "",
        mood=scene.mood,
    )


def shot_plan_to_create(plan: ShotPlan) -> ShotCreate:
    """ShotPlan → ShotCreate, field by field (no silent drops)."""
    return ShotCreate(
        shot_number=plan.shot_number,
        shot_type=plan.shot_type,
        camera_angle=plan.camera_angle,
        camera_movement=plan.camera_movement,
        duration=plan.duration,
        action=plan.action,
        emotion=plan.emotion,
        dialogue=plan.dialogue,
        image_prompt=plan.image_prompt,
    )


def shot_to_plan(shot: Shot) -> ShotPlan:
    """Persisted Shot → ShotPlan (idempotent replay of a confirmed storyboard)."""
    return ShotPlan(
        shot_number=shot.shot_number,
        shot_type=shot.shot_type,
        camera_angle=shot.camera_angle,
        camera_movement=shot.camera_movement,
        duration=shot.duration or 3.0,
        action=shot.action or "",
        emotion=shot.emotion,
        dialogue=shot.dialogue,
        image_prompt=shot.image_prompt,
    )
