"""P1-E3-T01: ToolExecutor defense-in-depth — never trusts the planner alone.

A hallucinated or forged shot id must be rejected (live + project ownership)
before the tool touches any Service, even if the planner passed it through.
"""

from app.agents.tools import ToolExecutor
from app.domain.agent import ToolOperation
from app.domain.episode import EpisodeCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.services import EpisodeService, ProjectService, SceneService, ShotService


def _make_project_shot(session, name: str):
    project = ProjectService(session).create_project(ProjectCreate(name=name))
    episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
    scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
    shot = ShotService(session).create_shot(scene.id, ShotCreate(shot_type="medium"))
    return project, shot


def test_executor_rejects_foreign_shot(session_factory) -> None:
    factory, _ = session_factory
    session = factory()
    project_a, shot_a = _make_project_shot(session, "A")
    _, shot_b = _make_project_shot(session, "B")

    executor = ToolExecutor(session, project_id=project_a.id)
    result = executor.execute(
        ToolOperation(
            tool="update_shot",
            arguments={"shot_id": shot_b.id, "patch": {"shot_type": "close_up"}},
        )
    )
    assert result.success is False
    assert "project" in (result.error or "")

    # shot B untouched — defense happened before any Service call
    assert ShotService(session).get_shot(shot_b.id).shot_type == "medium"
    # shot A untouched as well
    assert ShotService(session).get_shot(shot_a.id).shot_type == "medium"
    session.close()


def test_executor_rejects_deleted_shot(session_factory) -> None:
    factory, _ = session_factory
    session = factory()
    project, shot = _make_project_shot(session, "A")
    ShotService(session).delete_shot(shot.id)

    executor = ToolExecutor(session, project_id=project.id)
    result = executor.execute(ToolOperation(tool="get_shot", arguments={"shot_id": shot.id}))
    assert result.success is False
    assert "deleted" in (result.error or "").lower()
    session.close()


def test_executor_allows_project_shot(session_factory) -> None:
    factory, _ = session_factory
    session = factory()
    project, shot = _make_project_shot(session, "A")

    executor = ToolExecutor(session, project_id=project.id)
    result = executor.execute(ToolOperation(tool="get_shot", arguments={"shot_id": shot.id}))
    assert result.success is True
    assert result.data is not None
    session.close()
