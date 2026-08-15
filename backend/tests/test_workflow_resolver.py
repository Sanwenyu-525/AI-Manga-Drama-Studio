"""P4-T007: WorkflowResolver priority chain (request > project > system) + fallback."""

from fastapi.testclient import TestClient

from app.db.models import ProjectSetting
from app.services.workflow_resolver import WorkflowResolver

_IMAGE_DEFAULT = "default_image_api"
_SYSTEM_SENTINEL = _IMAGE_DEFAULT  # only template in the catalog today


def _make_project(client: TestClient) -> dict:
    return client.post("/api/v1/projects", json={"name": "P4T007"}).json()


def _set_project_workflow(session_factory, project_id: str, field: str, value: str) -> None:
    factory, _ = session_factory
    with factory() as session:
        row = session.get(ProjectSetting, project_id)
        if row is None:
            row = ProjectSetting(project_id=project_id)
            session.add(row)
        setattr(row, field, value)
        session.commit()


# --- priority chain ---

def test_request_override_wins_over_project_default(session_factory, client: TestClient) -> None:
    project = _make_project(client)
    _set_project_workflow(session_factory, project["id"], "default_image_workflow_id", "default_image_api")
    factory, _ = session_factory
    with factory() as session:
        resolved = WorkflowResolver(session).resolve(
            "image", request_workflow_id="default_image_api", project_id=project["id"]
        )
        assert resolved == "default_image_api"


def test_project_default_used_when_no_request_override(session_factory, client: TestClient) -> None:
    project = _make_project(client)
    _set_project_workflow(session_factory, project["id"], "default_image_workflow_id", "default_image_api")
    factory, _ = session_factory
    with factory() as session:
        resolved = WorkflowResolver(session).resolve("image", project_id=project["id"])
        assert resolved == "default_image_api"


def test_system_default_fallback(session_factory) -> None:
    factory, _ = session_factory
    with factory() as session:
        resolved = WorkflowResolver(session).resolve("image", project_id=None)
        assert resolved == _SYSTEM_SENTINEL


def test_video_project_default_field_for_video(session_factory, client: TestClient) -> None:
    """Resolver picks default_video_workflow_id for type=video (routing only — MVP
    generation still rejects video at create; the resolver itself is type-aware)."""
    project = _make_project(client)
    factory, _ = session_factory
    with factory() as session:
        row = session.get(ProjectSetting, project["id"])
        if row is None:
            row = ProjectSetting(project_id=project["id"])
            session.add(row)
        row.default_video_workflow_id = "default_image_api"
        session.commit()
    with factory() as session:
        resolved = WorkflowResolver(session).resolve("video", project_id=project["id"])
        assert resolved == "default_image_api"
    # image type ignores the video field -> system default
    with factory() as session:
        resolved_image = WorkflowResolver(session).resolve("image", project_id=project["id"])
        assert resolved_image == _SYSTEM_SENTINEL


# --- validation (422, never silent fallback) ---

def test_unknown_request_override_raises_422(session_factory) -> None:
    factory, _ = session_factory
    with factory() as session:
        import pytest

        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            WorkflowResolver(session).resolve("image", request_workflow_id="does_not_exist")


def test_unknown_project_default_raises_422(session_factory, client: TestClient) -> None:
    project = _make_project(client)
    _set_project_workflow(session_factory, project["id"], "default_image_workflow_id", "bogus_wf")
    import pytest

    from app.core.errors import ValidationError

    factory, _ = session_factory
    with factory() as session:
        with pytest.raises(ValidationError):
            WorkflowResolver(session).resolve("image", project_id=project["id"])


# --- GenerationService integration ---

def test_generation_omitted_workflow_resolves_and_persists(client: TestClient) -> None:
    shot = _make_shot(client)
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    assert created["workflow_id"] == _SYSTEM_SENTINEL


def test_generation_explicit_workflow_preserved(client: TestClient) -> None:
    shot = _make_shot(client)
    created = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "workflow_id": "default_image_api"},
    ).json()
    assert created["workflow_id"] == "default_image_api"


def test_generation_project_default_honored(client: TestClient, session_factory) -> None:
    project = client.post("/api/v1/projects", json={"name": "P4T007-default"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style"},
    ).json()
    _set_project_workflow(session_factory, project["id"], "default_image_workflow_id", "default_image_api")
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    assert created["workflow_id"] == "default_image_api"


def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P4T007-chain"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, night"},
    ).json()
