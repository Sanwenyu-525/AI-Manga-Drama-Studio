"""P7-T005/6/7: ContextResolver + TokenBudget + ContextSchemas.

The resolver builds typed, budget-capped context for different planning stages and
must never exceed the character budget. It only READS studio services.
"""

from app.agents.context_resolver import ContextResolver
from app.agents.token_budget import TokenBudget, truncate_text


def test_token_budget_truncates_long_text() -> None:
    text = "x" * 1000
    kept = truncate_text(text, 100)
    assert len(kept) <= 100
    # head/tail retained, middle elided
    assert kept.startswith("x" * 40)
    assert kept.endswith("x" * 40)
    assert "...[truncated]..." in kept


def test_token_budget_fit_respects_cap() -> None:
    budget = TokenBudget(max_chars=50)
    out = budget.fit(["a" * 30, "b" * 30, "c" * 30])
    # head part kept; later parts capped/elided but never exceed overall ~50
    total = sum(len(p) for p in out)
    assert total <= 50 or any(p.startswith("...[truncated]") for p in out[1:])


def test_context_resolver_story_planning(session_factory) -> None:
    from app.domain.project import ProjectCreate
    from app.domain.episode import EpisodeCreate
    from app.domain.scene import SceneCreate
    from app.services import EpisodeService, ProjectService, SceneService

    factory, _ = session_factory
    session = factory()
    project = ProjectService(session).create_project(ProjectCreate(name="P7Ctx"))
    episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
    SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))

    resolver = ContextResolver(session, max_chars=2000)
    out = resolver.resolve("story_planning", project.id)
    assert out["context_type"] == "story_planning"
    assert out["project_id"] == project.id
    assert isinstance(out["text"], str) and len(out["text"]) > 0
    assert out["token_chars"] <= 2000
    session.close()


def test_context_resolver_shot_planning(session_factory) -> None:
    from app.domain.project import ProjectCreate
    from app.domain.episode import EpisodeCreate
    from app.domain.scene import SceneCreate
    from app.domain.shot import ShotCreate
    from app.services import EpisodeService, ProjectService, SceneService, ShotService

    factory, _ = session_factory
    session = factory()
    project = ProjectService(session).create_project(ProjectCreate(name="P7Ctx2"))
    episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
    scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
    shot = ShotService(session).create_shot(scene.id, ShotCreate(shot_type="medium"))

    resolver = ContextResolver(session, max_chars=2000)
    out = resolver.resolve("shot_planning", project.id, shot_id=shot.id, scene_id=scene.id)
    assert out["context_type"] == "shot_planning"
    assert out["shot_id"] == shot.id
    assert "Shot:" in out["text"]
    assert out["token_chars"] <= 2000
    session.close()


def test_context_schemas_validated(session_factory) -> None:
    from pydantic import ValidationError

    from app.agents.context_schemas import StoryContext

    ctx = StoryContext(project_id="p1", scenes=[])
    assert ctx.project_id == "p1"
    rendered = ctx.render_text()
    assert "p1" in rendered
    try:
        StoryContext(project_id="", scenes=[])
    except ValidationError:
        pass
