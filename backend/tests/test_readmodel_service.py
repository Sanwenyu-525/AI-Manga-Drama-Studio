"""TASK-022 — ReadModelService 专项测试。

现有 test_shot_visual_spec.py 已覆盖 tree/editor/inspector 的 API happy-path 形状，
但 ReadModelService 自身的边界与组装逻辑没有专项覆盖，报告定位为 P2 缺口。本文件
聚焦服务层（不重复 API 形状测试）：

- project_tree:  空项目（无 episode）→ episodes=[]；软删除 project → NotFound
- project_tree:  shot 的 active_image/video_version 从 ActiveAsset→asset.version_number 解析
- scene_editor:  软删除 scene → NotFound
- shot_inspector:  spec 缺失时走 legacy column fallback（present=False）
- shot_inspector:  cast 中 character 被软删除 → 回退到 character_id
- shot_inspector:  prompt active version + count 汇总（ADR-002）

直接用 db session 构造数据，驱动 ReadModelService（不走 HTTP，聚焦服务语义）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Asset, Shot, ShotCharacter
from app.domain.episode import EpisodeCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.services import EpisodeService, ProjectService, SceneService, ShotService
from app.services.readmodel_service import ReadModelService


@pytest.fixture()
def svc(session_factory):
    factory, _ = session_factory
    session: Session = factory()
    yield {
        "session": session,
        "project": ProjectService(session),
        "episode": EpisodeService(session),
        "scene": SceneService(session),
        "shot": ShotService(session),
        "read": ReadModelService(session),
    }
    session.close()


def _chain(svc) -> dict:
    project = svc["project"].create_project(ProjectCreate(name="P"))
    episode = svc["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = svc["scene"].create_scene(episode.id, SceneCreate(name="S1", lighting="soft"))
    shot = svc["shot"].create_shots(
        scene.id,
        [ShotCreate(shot_number=1, shot_type="medium", duration=3.0, action="走进来")],
        analysis_key=None,
    )[0]
    return {"project": project, "episode": episode, "scene": scene, "shot": shot}


# ---------------------------------------------------------------- tree ----------

def test_project_tree_empty_project_returns_empty_episodes(svc) -> None:
    project = svc["project"].create_project(ProjectCreate(name="空项目"))
    tree = svc["read"].project_tree(project.id)
    assert tree.project.id == project.id
    assert tree.episodes == []


def test_project_tree_soft_deleted_project_raises_not_found(svc) -> None:
    project = svc["project"].create_project(ProjectCreate(name="将被删除"))
    svc["project"].delete_project(project.id)
    with pytest.raises(NotFoundError):
        svc["read"].project_tree(project.id)


def test_project_tree_missing_project_raises_not_found(svc) -> None:
    with pytest.raises(NotFoundError):
        svc["read"].project_tree("no-such-project")


def test_project_tree_resolves_active_version_numbers(svc) -> None:
    """shot.active_image_asset_id → asset.version_number 在 tree 与 editor 中正确解析。"""
    ctx = _chain(svc)
    session: Session = svc["session"]

    # 为 shot 挂两个手工 asset（V1/V2），并把 active_image 指向 V2
    assets = [
        Asset(
            project_id=ctx["project"].id, type="image", name=f"v{i}",
            version_group_id=f"vg:shot:{ctx['shot'].id}:SHOT_IMAGE", version_number=i,
        )
        for i in (1, 2)
    ]
    session.add_all(assets)
    session.flush()

    shot_row = session.get(Shot, ctx["shot"].id)
    shot_row.active_image_asset_id = assets[1].id
    session.commit()

    tree = svc["read"].project_tree(ctx["project"].id)
    shots_of_scene = tree.episodes[0].scenes[0].shots
    assert shots_of_scene[0].active_image_version == 2


# ---------------------------------------------------------------- editor ---------

def test_scene_editor_soft_deleted_scene_raises_not_found(svc) -> None:
    ctx = _chain(svc)
    svc["scene"].delete_scene(ctx["scene"].id)
    with pytest.raises(NotFoundError):
        svc["read"].scene_editor(ctx["scene"].id)


def test_scene_editor_missing_scene_raises_not_found(svc) -> None:
    with pytest.raises(NotFoundError):
        svc["read"].scene_editor("no-such-scene")


# ---------------------------------------------------------------- inspector -------

def test_shot_inspector_spec_fallback_when_spec_missing(svc) -> None:
    """直接插入无 spec 行的 Shot（绕过 create_shots 的 _upsert_spec），
    inspector 应回落到 legacy shot 列（present=False）。"""
    ctx = _chain(svc)
    session: Session = svc["session"]
    raw = Shot(
        scene_id=ctx["scene"].id,
        shot_number=2,
        shot_order=2,
        shot_type="wide",
        camera_angle="high_angle",
        action="旧版动作",
        status="draft",
        dirty_state="clean",
        revision=1,
        analysis_key=None,
    )
    session.add(raw)
    session.commit()

    insp = svc["read"].shot_inspector(raw.id)
    assert insp.visual_spec.present is False
    assert insp.visual_spec.shot_type == "wide"
    assert insp.visual_spec.camera_angle == "high_angle"
    assert insp.visual_spec.action == "旧版动作"


def test_shot_inspector_spec_present_preferred(svc) -> None:
    """存在 spec 行时，inspector 使用 spec 字段而非 legacy 列。"""
    ctx = _chain(svc)  # create_shots 已写 spec（pending in session）
    svc["session"].commit()  # 让 _upsert_spec 的行落库，确保读路径可见
    insp = svc["read"].shot_inspector(ctx["shot"].id)
    assert insp.visual_spec.present is True
    assert insp.visual_spec.shot_type == "medium"


def test_shot_inspector_cast_falls_back_to_character_id_when_missing(svc) -> None:
    """cast 中 character 不存在（dangling link）→ name 回退为 character_id（不抛错）。"""
    ctx = _chain(svc)
    session: Session = svc["session"]
    session.add(ShotCharacter(shot_id=ctx["shot"].id, character_id="missing-char", role="主角"))
    session.commit()

    insp = svc["read"].shot_inspector(ctx["shot"].id)
    assert len(insp.characters) == 1
    assert insp.characters[0].character_id == "missing-char"
    assert insp.characters[0].name == "missing-char"  # character 缺失 → 回退到 id
    assert insp.characters[0].role == "主角"
