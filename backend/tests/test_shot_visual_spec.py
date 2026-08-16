"""P2-T005 ShotVisualSpec + P2-T011/T012/T013 Read Model tests.

Covers:
- spec write-through (create/update persist a 1:1 shot_visual_specs row)
- read preference (spec fields win) + fallback (legacy inline shot columns)
- agent update_shot regression (the Agent path still syncs the spec)
- storyboard aggregation regression (spec-fallback shot_type)
- Read Model shapes: /projects/{id}/tree, /scenes/{id}/editor, /shots/{id}/inspector
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ShotVisualSpec
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


def _chain(services) -> dict:
    project = services["project"].create_project(ProjectCreate(name="P"))
    episode = services["episode"].create_episode(project.id, EpisodeCreate(title="E1"))
    scene = services["scene"].create_scene(episode.id, SceneCreate(name="S1", lighting="soft warm"))
    return {"project": project, "episode": episode, "scene": scene}


# ---------------------------------------------------------------- spec sync ----

def test_create_shot_writes_spec(services, session_factory) -> None:
    ctx = _chain(services)
    shot = services["shot"].create_shot(
        ctx["scene"].id,
        ShotCreate(shot_type="close_up", camera_angle="low_angle", camera_movement="dolly",
                   action="fight", emotion="tense"),
    )
    factory, _ = session_factory
    with factory() as session:
        spec = session.get(ShotVisualSpec, shot.id)
        assert spec is not None
        assert spec.shot_type == "close_up"
        assert spec.camera_angle == "low_angle"
        assert spec.camera_movement == "dolly"
        assert spec.action == "fight"
        assert spec.mood == "tense"          # spec.mood ↔ shot.emotion
        assert spec.lighting == "soft warm"    # inherited from the scene's lighting
        assert spec.environment is None         # no legacy environment column populated


def test_update_shot_upserts_spec(services, session_factory) -> None:
    ctx = _chain(services)
    shot = services["shot"].create_shot(ctx["scene"].id, ShotCreate(shot_type="medium"))
    updated = services["shot"].update_shot(
        shot.id, 1, ShotUpdate(camera_angle="high_angle", camera_movement="pan")
    )
    assert updated.revision == 2
    factory, _ = session_factory
    with factory() as session:
        spec = session.get(ShotVisualSpec, shot.id)
        assert spec is not None
        assert spec.camera_angle == "high_angle"
        assert spec.camera_movement == "pan"


def test_read_prefers_spec_fields(services) -> None:
    ctx = _chain(services)
    shot = services["shot"].create_shot(
        ctx["scene"].id,
        ShotCreate(shot_type="close_up", camera_angle="low_angle", camera_movement="dolly", emotion="tense"),
    )
    read = services["shot"].get_shot(shot.id)
    assert read.shot_type == "close_up"
    assert read.camera_angle == "low_angle"
    assert read.camera_movement == "dolly"
    assert read.emotion == "tense"


def test_fallback_when_spec_missing(services, session_factory) -> None:
    """Legacy shot (no spec row) reads its inline columns — backward compat."""
    ctx = _chain(services)
    shot = services["shot"].create_shot(
        ctx["scene"].id,
        ShotCreate(shot_type="wide", camera_angle="high_angle", camera_movement="static", emotion="calm"),
    )
    factory, _ = session_factory
    with factory() as session:
        session.query(ShotVisualSpec).filter(ShotVisualSpec.shot_id == shot.id).delete()
        session.commit()
    read = services["shot"].get_shot(shot.id)
    assert read.shot_type == "wide"
    assert read.camera_angle == "high_angle"
    assert read.camera_movement == "static"
    assert read.emotion == "calm"


def test_storyboard_summary_uses_spec_shot_type(services, session_factory) -> None:
    ctx = _chain(services)
    shot = services["shot"].create_shot(ctx["scene"].id, ShotCreate(shot_type="close_up"))
    sb = services["shot"].get_storyboard(ctx["scene"].id)
    assert sb.shots[0].shot_type == "close_up"
    # mutate legacy column directly (simulate a legacy row whose shot_type differs),
    # then confirm the summary still prefers the spec value.
    factory, _ = session_factory
    with factory() as session:
        row = session.get(ShotVisualSpec, shot.id)
        row.shot_type = "wide"
        session.commit()
    sb2 = services["shot"].get_storyboard(ctx["scene"].id)
    assert sb2.shots[0].shot_type == "wide"


def test_agent_update_shot_syncs_spec(client: TestClient) -> None:
    """Agent path (Director update_shot via ShotService) must still write-through the spec."""
    import time

    project = client.post("/api/v1/projects", json={"name": "SpecAgent"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "prompt"},
    ).json()

    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": project["id"],
            "message": "把这个镜头改成近景。",
            "selection": {"shot_ids": [shot["id"]], "workspace": "storyboard", "scene_id": scene["id"]},
        },
    )
    assert resp.status_code == 202
    run_id = resp.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in ("waiting_human", "waiting_approval", "completed", "failed", "cancelled"):
            break
        time.sleep(0.05)
    # P7: update_shot parks in WAITING_HUMAN — approve to apply via ShotService
    if run["status"] in ("waiting_human", "waiting_approval"):
        assert len(run["pending_proposals"]) == 1
        client.post(f"/api/v1/agent/runs/{run_id}/resume", json={"decision": "approve"})
        while time.monotonic() < deadline:
            run = client.get(f"/api/v1/agent/runs/{run_id}").json()
            if run["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.05)
    assert run["status"] == "completed", run.get("result")
    updated = client.get(f"/api/v1/shots/{shot['id']}").json()
    assert updated["shot_type"] == "close_up"
    inspector = client.get(f"/api/v1/shots/{shot['id']}/inspector").json()
    assert inspector["visual_spec"]["present"] is True
    assert inspector["visual_spec"]["shot_type"] == "close_up"


# ---------------------------------------------------------------- read models --

def _make_shots(client: TestClient, scene_id: str, n: int = 2) -> list[dict]:
    return [
        client.post(
            f"/api/v1/scenes/{scene_id}/shots",
            json={
                "shot_type": "close_up" if i == 0 else "medium",
                "camera_angle": "low_angle",
                "camera_movement": "dolly",
                "emotion": "tense",
            },
        ).json()
        for i in range(n)
    ]


def test_project_tree_shape(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Tree"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    _make_shots(client, scene["id"])
    # a second scene to verify nested scene_count + shot_count
    scene2 = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S2"}
    ).json()
    _make_shots(client, scene2["id"], n=1)

    tree = client.get(f"/api/v1/projects/{project['id']}/tree")
    assert tree.status_code == 200
    data = tree.json()
    assert data["project"]["id"] == project["id"]
    assert len(data["episodes"]) == 1
    ep = data["episodes"][0]
    assert ep["scene_count"] == 2
    scenes = {s["id"]: s for s in ep["scenes"]}
    assert scenes[scene["id"]]["shot_count"] == 2
    assert scenes[scene["id"]]["shots"][0]["shot_type"] == "close_up"
    assert scenes[scene["id"]]["shots"][0]["status"] == "draft"
    assert "revision" in scenes[scene["id"]]["shots"][0]
    assert "active_image_version" in scenes[scene["id"]]["shots"][0]
    assert scenes[scene2["id"]]["shot_count"] == 1


def test_scene_editor_shape(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Editor"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1", "lighting": "soft warm"}
    ).json()
    _make_shots(client, scene["id"])

    editor = client.get(f"/api/v1/scenes/{scene['id']}/editor")
    assert editor.status_code == 200
    data = editor.json()
    assert data["scene"]["id"] == scene["id"]
    assert len(data["shots"]) == 2
    first = data["shots"][0]
    assert first["shot_type"] == "close_up"
    assert first["spec_summary"]["camera_angle"] == "low_angle"
    assert first["spec_summary"]["camera_movement"] == "dolly"
    assert first["spec_summary"]["mood"] == "tense"
    assert "active_image_version" in first
    assert "character_names" in first


def test_shot_inspector_shape(client: TestClient) -> None:
    from app.db.session import session_factory_provider
    from app.db.models import ShotCharacter

    project = client.post("/api/v1/projects", json={"name": "Insp"}).json()
    character = client.post(
        f"/api/v1/projects/{project['id']}/characters",
        json={"name": "沈亦"},
    ).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={
            "shot_type": "close_up",
            "camera_angle": "low_angle",
            "camera_movement": "dolly",
            "emotion": "tense",
            "character_ids": [character["id"]],
        },
    ).json()
    # set a per-shot costume on the link (shot_characters.costume_id)
    factory = session_factory_provider()
    with factory() as session:
        link = session.query(ShotCharacter).filter(
            ShotCharacter.shot_id == shot["id"], ShotCharacter.character_id == character["id"]
        ).first()
        link.costume_id = "costume_a"
        session.commit()

    inspector = client.get(f"/api/v1/shots/{shot['id']}/inspector")
    assert inspector.status_code == 200
    data = inspector.json()
    assert data["shot"]["shot_type"] == "close_up"
    assert data["shot"]["camera_angle"] == "low_angle"
    spec = data["visual_spec"]
    assert spec["present"] is True
    assert spec["mood"] == "tense"
    assert spec["shot_type"] == "close_up"
    assert "active_image_version" in data
    assert "active_video_version" in data
    assert isinstance(data["prompts"], dict)
    assert len(data["characters"]) == 1
    cast = data["characters"][0]
    assert cast["name"] == "沈亦"
    assert cast["costume_id"] == "costume_a"


def test_inspector_from_legacy_shot(client: TestClient) -> None:
    """A shot without a spec row surfaces the legacy inline fields (fallback)."""
    from app.db.session import session_factory_provider

    project = client.post("/api/v1/projects", json={"name": "Legacy"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(
        f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}
    ).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "camera_angle": "high_angle", "emotion": "calm"},
    ).json()
    factory = session_factory_provider()
    with factory() as session:
        session.query(ShotVisualSpec).filter(ShotVisualSpec.shot_id == shot["id"]).delete()
        session.commit()

    inspector = client.get(f"/api/v1/shots/{shot['id']}/inspector").json()
    assert inspector["visual_spec"]["present"] is False
    assert inspector["visual_spec"]["shot_type"] == "medium"
    assert inspector["visual_spec"]["camera_angle"] == "high_angle"
    assert inspector["visual_spec"]["mood"] == "calm"
    assert inspector["shot"]["shot_type"] == "medium"
