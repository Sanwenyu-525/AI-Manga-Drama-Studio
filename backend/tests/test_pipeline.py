"""C2 一键成片 Pipeline tests — run(analyze preview→waiting_confirm) →
confirm(scenes+shots+images) → finalize(timeline+render) → completed, plus resume.

The long LLM stages run through the Operation mechanism (202 + poll).
FakeLLMGateway (default) keeps them fast; mock image provider is driven manually
(like test_voiceover) so timeline sequence can bind real images.
"""

import asyncio
import time

from fastapi.testclient import TestClient

from app.generations.worker import run_generation
from app.db.models import Generation, Shot

NOVEL_TEXT = (
    "夜色降临，天台上沈亦握着篮球。顾言说：'最后一种打法，要么赢，要么散。'"
    "第二天体育馆决赛，哨声响起，沈亦带球突破投篮，球进，全场欢呼。"
)


def _setup_episode(client: TestClient) -> str:
    project = client.post("/api/v1/projects", json={"name": "Pipeline"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes",
        json={"title": "第一集", "source_text": NOVEL_TEXT},
    ).json()
    return episode["id"]


def _wait_operation(client: TestClient, op_id: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        op = client.get(f"/api/v1/operations/{op_id}").json()
        if op["status"] in ("completed", "failed"):
            return op
        time.sleep(0.05)
    raise TimeoutError(f"operation {op_id} did not finish in {timeout}s")


def _run(client: TestClient, episode_id: str) -> dict:
    resp = client.post(f"/api/v1/episodes/{episode_id}/pipeline/run")
    assert resp.status_code == 202, resp.text
    op = _wait_operation(client, resp.json()["operation_id"])
    assert op["status"] == "completed", op.get("error")
    latest = client.get(f"/api/v1/episodes/{episode_id}/pipeline/latest").json()
    return latest


def _confirm(client: TestClient, episode_id: str, pipeline_id: str) -> dict:
    resp = client.post(f"/api/v1/episodes/{episode_id}/pipeline/{pipeline_id}/confirm")
    assert resp.status_code == 202, resp.text
    op = _wait_operation(client, resp.json()["operation_id"], timeout=60.0)
    assert op["status"] == "completed", op.get("error")
    return client.get(f"/api/v1/episodes/{episode_id}/pipeline/latest").json()


def _episode_image_generations(session_factory, episode_id: str) -> list[dict]:
    """[(generation_id, status)] of all image generations for the episode's shots."""
    from sqlalchemy import select, text

    from app.db.models import Generation

    factory = session_factory[0]
    out: list[dict] = []
    with factory() as s:
        shot_ids = [
            row[0]
            for row in s.execute(
                text(
                    "SELECT s.id FROM shots s JOIN scenes sc ON s.scene_id=sc.id "
                    "JOIN episodes e ON sc.episode_id=e.id WHERE e.id=:eid AND s.deleted_at IS NULL"
                ),
                {"eid": episode_id},
            )
        ]
        if not shot_ids:
            return out
        rows = s.execute(
            select(Generation.id, Generation.status).where(
                Generation.shot_id.in_(shot_ids), Generation.type == "image"
            )
        )
        out = [{"id": r[0], "status": r[1]} for r in rows]
    return out


def _drive_episode_images(client: TestClient, session_factory, episode_id: str) -> None:
    """Manually drive all queued/running image generations for the episode's shots."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        gens = _episode_image_generations(session_factory, episode_id)
        pending = [g for g in gens if g["status"] in ("queued", "running")]
        if not pending:
            return
        for g in pending:
            asyncio.run(run_generation(g["id"]))
        time.sleep(0.05)


def test_pipeline_run_waiting_confirm(client: TestClient) -> None:
    episode_id = _setup_episode(client)
    latest = _run(client, episode_id)
    assert latest["status"] == "waiting_confirm"
    assert latest["stages"]["analyze"] == "done"
    assert latest["snapshot_id"]
    assert latest["current_stage"] is None


def test_pipeline_confirm_finalize_completes(client: TestClient, session_factory) -> None:
    episode_id = _setup_episode(client)
    latest = _run(client, episode_id)
    pipeline_id = latest["id"]

    latest = _confirm(client, episode_id, pipeline_id)
    assert latest["stages"]["shots"] == "done"
    assert latest["stages"]["images"] == "done"
    assert latest["status"] == "running"
    assert latest["current_stage"] == "images"

    # drive the queued image generations so timeline sequence can bind real assets
    _drive_episode_images(client, session_factory, episode_id)

    resp = client.post(f"/api/v1/episodes/{episode_id}/pipeline/{pipeline_id}/finalize")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pipeline"]["status"] == "completed"
    assert body["pipeline"]["stages"]["timeline"] == "done"
    assert body["pipeline"]["stages"]["render"] == "done"

    # timeline exists with a render generation queued
    tl = client.get(f"/api/v1/episodes/{episode_id}/timeline").json()
    assert tl["tracks"]
    render_gen = _latest_render_generation(session_factory, episode_id)
    assert render_gen is not None


def test_pipeline_confirm_requires_analysis(client: TestClient) -> None:
    episode_id = _setup_episode(client)
    # no pipeline yet → confirm on a bogus id must fail (operation wraps the error)
    resp = client.post(f"/api/v1/episodes/{episode_id}/pipeline/nope/confirm")
    assert resp.status_code == 202
    op = _wait_operation(client, resp.json()["operation_id"])
    assert op["status"] == "failed"
    assert "Pipeline does not exist" in op.get("error", "")


def test_pipeline_resume_completes_from_images(client: TestClient, session_factory) -> None:
    """Resume continues from the first non-done stage (here: timeline/render)."""
    episode_id = _setup_episode(client)
    latest = _run(client, episode_id)
    pipeline_id = latest["id"]
    latest = _confirm(client, episode_id, pipeline_id)
    assert latest["status"] == "running"
    _drive_episode_images(client, session_factory, episode_id)

    # simulate a crash after images: a fresh resume should finish timeline+render
    resp = client.post(f"/api/v1/episodes/{episode_id}/pipeline/{pipeline_id}/resume")
    assert resp.status_code == 202, resp.text
    op = _wait_operation(client, resp.json()["operation_id"], timeout=60.0)
    assert op["status"] == "completed", op.get("error")
    final = client.get(f"/api/v1/episodes/{episode_id}/pipeline/latest").json()
    assert final["status"] == "completed"


def _latest_render_generation(session_factory, episode_id: str) -> str | None:
    """Latest type=render generation for the episode (via its timeline)."""
    from sqlalchemy import select, text

    from app.db.models import Generation, Timeline

    factory = session_factory[0]
    with factory() as s:
        timeline_id = s.execute(
            text("SELECT t.id FROM timelines t WHERE t.episode_id=:eid LIMIT 1"),
            {"eid": episode_id},
        ).scalar()
        if not timeline_id:
            return None
        # render generations carry their timeline in parameters JSON — match by type
        # + most recent (test DBs are isolated per case).
        row = s.execute(
            select(Generation.id).where(Generation.type == "render").order_by(Generation.created_at.desc()).limit(1)
        ).first()
        return row[0] if row else None
