"""Service unit tests (mvp-spec §95): ShotService revision semantics, SceneService counting."""

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Project
from app.domain.episode import EpisodeCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate, ShotUpdate
from app.services import EpisodeService, ProjectService, SceneService, ShotService


@pytest.fixture()
def services(session_factory):
    factory, _ = session_factory
    session: Session = factory()
    yield {
        "project": ProjectService(session),
        "episode": EpisodeService(session),
        "scene": SceneService(session),
        "shot": ShotService(session),
    }
    session.close()


def test_shot_update_increments_revision_and_marks_dirty(services) -> None:
    project = services["project"].create_project(ProjectCreate(name="P"))
    episode = services["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = services["scene"].create_scene(episode.id, SceneCreate(name="S1"))
    shot = services["shot"].create_shot(scene.id, ShotCreate(shot_type="medium"))

    assert shot.revision == 1
    updated = services["shot"].update_shot(shot.id, 1, ShotUpdate(shot_type="close_up", emotion="tense"))
    assert updated.revision == 2
    assert updated.shot_type == "close_up"
    assert updated.dirty_state == "dirty_image"

    # non-visual fields don't dirty the image
    updated2 = services["shot"].update_shot(shot.id, 2, ShotUpdate(status="approved"))
    assert updated2.revision == 3
    assert updated2.dirty_state == "dirty_image"  # dirty state preserved, not reset


def test_stale_revision_raises_conflict(services) -> None:
    project = services["project"].create_project(ProjectCreate(name="P"))
    episode = services["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = services["scene"].create_scene(episode.id, SceneCreate(name="S1"))
    shot = services["shot"].create_shot(scene.id, ShotCreate(shot_type="medium"))

    services["shot"].update_shot(shot.id, 1, ShotUpdate(duration=4.0))
    with pytest.raises(ConflictError):
        services["shot"].update_shot(shot.id, 1, ShotUpdate(duration=5.0))


def test_shot_number_auto_increment_and_delete(services) -> None:
    project = services["project"].create_project(ProjectCreate(name="P"))
    episode = services["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = services["scene"].create_scene(episode.id, SceneCreate(name="S1"))

    s1 = services["shot"].create_shot(scene.id, ShotCreate(shot_type="wide"))
    s2 = services["shot"].create_shot(scene.id, ShotCreate(shot_type="close_up"))
    assert (s1.shot_number, s2.shot_number) == (1, 2)

    services["shot"].delete_shot(s1.id)
    with pytest.raises(NotFoundError):
        services["shot"].get_shot(s1.id)
    remaining = services["shot"].list_shots(scene.id)
    assert [s.id for s in remaining] == [s2.id]
    # numbering continues past the soft-deleted shot
    s3 = services["shot"].create_shot(scene.id, ShotCreate(shot_type="full"))
    assert s3.shot_number == 3


def test_scene_shot_count(services) -> None:
    project = services["project"].create_project(ProjectCreate(name="P"))
    episode = services["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = services["scene"].create_scene(episode.id, SceneCreate(name="S1"))
    services["shot"].create_shot(scene.id, ShotCreate(shot_type="wide"))
    services["shot"].create_shot(scene.id, ShotCreate(shot_type="medium"))

    fetched = services["scene"].get_scene(scene.id)
    assert fetched.shot_count == 2
    listed = services["scene"].list_scenes(episode.id)
    assert listed[0].shot_count == 2


def test_reorder_updates_numbers(services) -> None:
    project = services["project"].create_project(ProjectCreate(name="P"))
    episode = services["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = services["scene"].create_scene(episode.id, SceneCreate(name="S1"))
    s1 = services["shot"].create_shot(scene.id, ShotCreate(shot_type="wide"))
    s2 = services["shot"].create_shot(scene.id, ShotCreate(shot_type="medium"))

    reordered = services["shot"].reorder_shots(scene.id, [s2.id, s1.id])
    assert [s.shot_number for s in reordered] == [1, 2]
    assert [s.id for s in reordered] == [s2.id, s1.id]
