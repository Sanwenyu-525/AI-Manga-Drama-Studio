"""P1-E6-T01: the REAL worker DB-poll loop — not the execution function.

The loop must claim a queued generation from the DB and drive it to completion.
(The conftest client fixture routes jobs to the test DB via session_factory_provider;
this test overrides the provider the same way, standalone.)
"""

import asyncio

from app.db import session as db_session_module
from app.db.models import Generation
from app.domain.episode import EpisodeCreate
from app.domain.generation import GenerationCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate
from app.generations import worker as worker_module
from app.generations.worker import worker_loop
from app.services import EpisodeService, GenerationService, ProjectService, SceneService, ShotService


def test_worker_loop_claims_and_completes_generation(session_factory, monkeypatch) -> None:
    factory, _ = session_factory
    monkeypatch.setattr(db_session_module, "session_factory_provider", lambda: factory)
    monkeypatch.setattr(worker_module, "POLL_INTERVAL_SECONDS", 0.02)

    with factory() as session:
        project = ProjectService(session).create_project(ProjectCreate(name="WorkerLoop"))
        episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
        scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
        shot = ShotService(session).create_shot(
            scene.id, ShotCreate(shot_type="medium", image_prompt="worker loop test")
        )
        generation = GenerationService(session).create_generation(shot.id, GenerationCreate(type="image"))
        gen_id = generation.id

    async def _drive() -> str:
        loop_task = asyncio.create_task(worker_loop())
        try:
            for _ in range(200):
                await asyncio.sleep(0.05)
                with factory() as session:
                    status = session.get(Generation, gen_id).status
                if status == "completed":
                    return status
            raise TimeoutError("worker loop never completed the generation")
        finally:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass

    status = asyncio.run(_drive())
    assert status == "completed"

    # output was attached by the loop (asset + active version)
    with factory() as session:
        done = session.get(Generation, gen_id)
        assert done.output_asset_id is not None
        assert done.progress == 100
