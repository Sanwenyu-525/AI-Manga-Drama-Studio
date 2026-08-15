"""P1-E1-T01: service-level transaction / idempotency guarantees (direct DB assertions).

- A failure anywhere in a confirm flow rolls back EVERYTHING (no partial rows,
  no committed idempotency key).
- Re-submitting the same request is a no-op that does NOT call the LLM again and
  replays the persisted rows exactly.
"""

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Episode, Scene, Shot
from app.domain.episode import EpisodeCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.llm.fake import FakeLLMGateway
from app.services import EpisodeService, ProjectService, SceneService
from app.services.script_service import ScriptService


def _setup(session_factory) -> tuple[Session, Episode]:
    factory, _ = session_factory
    session: Session = factory()
    project = ProjectService(session).create_project(ProjectCreate(name="TX"))
    episode = EpisodeService(session).create_episode(
        project.id, EpisodeCreate(title="E1", source_text="夜色降临，城市天台。\n" * 100)
    )
    return session, episode


def _live_scene_count(session: Session, episode_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(Scene).where(
            Scene.episode_id == episode_id, Scene.deleted_at.is_(None)
        )
    ) or 0


def _live_shot_count(session: Session, scene_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(Shot).where(
            Shot.scene_id == scene_id, Shot.deleted_at.is_(None)
        )
    ) or 0


def test_analyze_failure_rolls_back_everything(session_factory, monkeypatch) -> None:
    """Nth scene write fails → first N-1 must not remain in the DB."""
    from app.services.scene_service import SceneService as SceneSvc

    session, episode = _setup(session_factory)
    original = SceneSvc.create_scenes

    def flaky(self, episode_id, datas, analysis_key=None):
        original(self, episode_id, datas[:1], analysis_key=analysis_key)  # add 1 row, no commit
        raise RuntimeError("injected mid-batch failure")

    monkeypatch.setattr(SceneSvc, "create_scenes", flaky)
    with pytest.raises(RuntimeError):
        asyncio.run(ScriptService(session, FakeLLMGateway()).analyze_episode(episode.id))

    session.expire_all()
    assert _live_scene_count(session, episode.id) == 0
    # the idempotency key is only committed with a successful batch
    assert session.get(Episode, episode.id).analysis_key is None
    session.close()


def test_analyze_idempotent_second_run_skips_llm(session_factory) -> None:
    session, episode = _setup(session_factory)
    llm = FakeLLMGateway()
    calls = {"n": 0}
    original_list = llm.structured_list

    async def counting(schema, system, prompt):
        calls["n"] += 1
        return await original_list(schema, system, prompt)

    llm.structured_list = counting  # type: ignore[method-assign]

    service = ScriptService(session, llm)
    first = asyncio.run(service.analyze_episode(episode.id))
    assert calls["n"] == 1
    assert len(first.created_scene_ids) >= 2

    second = asyncio.run(service.analyze_episode(episode.id))
    assert second.created_scene_ids == first.created_scene_ids
    assert calls["n"] == 1  # no LLM call on the idempotent re-submission
    # replayed plans are field-identical to the persisted rows (round trip)
    assert second.scene_plans == first.scene_plans
    session.close()


def test_generate_shots_failure_rolls_back_everything(session_factory, monkeypatch) -> None:
    from app.services.shot_service import ShotService as ShotSvc

    session, episode = _setup(session_factory)
    scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
    original = ShotSvc.create_shots

    def flaky(self, scene_id, datas, analysis_key=None):
        original(self, scene_id, datas[:1], analysis_key=analysis_key)
        raise RuntimeError("injected mid-batch failure")

    monkeypatch.setattr(ShotSvc, "create_shots", flaky)
    with pytest.raises(RuntimeError):
        asyncio.run(ScriptService(session, FakeLLMGateway()).generate_shot_plans(scene.id))

    session.expire_all()
    assert _live_shot_count(session, scene.id) == 0
    assert session.get(Scene, scene.id).storyboard_key is None
    session.close()


def test_generate_shots_idempotent_second_run_skips_llm(session_factory) -> None:
    session, episode = _setup(session_factory)
    scene = SceneService(session).create_scene(
        episode.id, SceneCreate(name="S1", location_id="L1", time_of_day="night")
    )
    llm = FakeLLMGateway()
    calls = {"n": 0}
    original_list = llm.structured_list

    async def counting(schema, system, prompt):
        calls["n"] += 1
        return await original_list(schema, system, prompt)

    llm.structured_list = counting  # type: ignore[method-assign]

    service = ScriptService(session, llm)
    first = asyncio.run(service.generate_shot_plans(scene.id))
    assert calls["n"] == 1
    assert len(first.created_shot_ids) == 6

    second = asyncio.run(service.generate_shot_plans(scene.id))
    assert second.created_shot_ids == first.created_shot_ids
    assert calls["n"] == 1  # no LLM call on the idempotent re-submission
    assert second.shot_plans == first.shot_plans
    session.close()
