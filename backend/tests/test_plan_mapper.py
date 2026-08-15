"""P1-E1-T01: explicit Plan ↔ Domain mapping — no field silently dropped.

Regression: ScriptService used to persist ScenePlan via SceneCreate(**plan.model_dump()),
which silently dropped title/location/time (Pydantic extra-field ignore). The
explicit mapper below is the only mapping path; every field is asserted.
"""

from app.db.models import Scene, Shot
from app.domain.analysis import ScenePlan, ShotPlan
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.services.plan_mapper import (
    scene_plan_to_create,
    scene_to_plan,
    shot_plan_to_create,
    shot_to_plan,
)


def test_scene_plan_maps_every_field_explicitly() -> None:
    plan = ScenePlan(
        scene_number=3,
        title="天台对决",
        location="城市天台",
        time="night",
        description="主角与对手在深夜的天台对峙。",
        mood="tense",
    )
    create = scene_plan_to_create(plan)

    # ScenePlan field → SceneCreate field (the exact mapping that used to be lost):
    assert create.scene_number == plan.scene_number
    assert create.name == plan.title          # title → name
    assert create.location_id == plan.location  # location → location_id
    assert create.time_of_day == plan.time    # time → time_of_day
    assert create.description == plan.description
    assert create.mood == plan.mood

    # contract: every ScenePlan field is covered by the mapper's target schema
    assert set(ScenePlan.model_fields) == {
        "scene_number", "title", "location", "time", "description", "mood",
    }
    assert set(SceneCreate.model_fields) >= {
        "scene_number", "name", "location_id", "time_of_day", "description", "mood",
    }


def test_scene_plan_optional_fields_map_to_none() -> None:
    plan = ScenePlan(scene_number=1, title="T", location="L", description="D")
    create = scene_plan_to_create(plan)
    assert create.time_of_day is None
    assert create.mood is None


def test_shot_plan_maps_every_field_explicitly() -> None:
    plan = ShotPlan(
        shot_number=4,
        shot_type="close_up",
        camera_angle="low_angle",
        camera_movement="dolly",
        duration=4.5,
        action="主角握紧篮球",
        emotion="fear",
        dialogue="别过来。",
        image_prompt="close_up shot, manga style",
    )
    create = shot_plan_to_create(plan)

    assert create.shot_number == plan.shot_number
    assert create.shot_type == plan.shot_type
    assert create.camera_angle == plan.camera_angle
    assert create.camera_movement == plan.camera_movement
    assert create.duration == plan.duration
    assert create.action == plan.action
    assert create.emotion == plan.emotion
    assert create.dialogue == plan.dialogue
    assert create.image_prompt == plan.image_prompt

    # contract: every ShotPlan field is covered by the mapper's target schema
    assert set(ShotPlan.model_fields) == {
        "shot_number", "shot_type", "camera_angle", "camera_movement",
        "duration", "action", "emotion", "dialogue", "image_prompt",
    }
    assert set(ShotCreate.model_fields) >= {
        "shot_number", "shot_type", "camera_angle", "camera_movement",
        "duration", "action", "emotion", "dialogue", "image_prompt",
    }


def test_scene_row_round_trips_to_plan() -> None:
    scene = Scene(
        episode_id="e1",
        scene_number=2,
        name="学校体育馆",
        location_id="体育馆",
        time_of_day="day",
        description="决赛前的最后一练。",
        mood="excited",
    )
    plan = scene_to_plan(scene)
    assert plan == ScenePlan(
        scene_number=2,
        title="学校体育馆",
        location="体育馆",
        time="day",
        description="决赛前的最后一练。",
        mood="excited",
    )
    # replaying the plan back must reproduce the same row fields
    create = scene_plan_to_create(plan)
    assert create.name == "学校体育馆"
    assert create.location_id == "体育馆"
    assert create.time_of_day == "day"


def test_shot_row_round_trips_to_plan() -> None:
    shot = Shot(
        scene_id="s1",
        shot_number=1,
        shot_type="wide",
        camera_angle="eye_level",
        camera_movement="static",
        duration=3.0,
        action="球员入场",
        emotion="calm",
        dialogue=None,
        image_prompt="wide shot, arena",
    )
    plan = shot_to_plan(shot)
    assert plan == ShotPlan(
        shot_number=1,
        shot_type="wide",
        camera_angle="eye_level",
        camera_movement="static",
        duration=3.0,
        action="球员入场",
        emotion="calm",
        dialogue=None,
        image_prompt="wide shot, arena",
    )
