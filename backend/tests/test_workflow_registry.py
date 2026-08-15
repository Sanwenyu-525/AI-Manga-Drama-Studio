"""P4-T004: WorkflowTemplate/WorkflowVersion registration + catalog + versions list."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.models import WorkflowTemplate, WorkflowVersion


def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P4T004"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style"},
    ).json()


def test_workflows_catalog_returns_registered_template(client: TestClient) -> None:
    """GET /workflows is backed by the registered template (compat with legacy catalog)."""
    resp = client.get("/api/v1/workflows")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert any(item["id"] == "default_image_api" for item in items)

    wf = next(item for item in items if item["id"] == "default_image_api")
    assert wf["is_default"] is True
    assert wf["file"] == "default_image_api.json"
    assert wf["exists"] is True
    assert wf["valid_json"] is True
    assert wf["output_node_class"] == "SaveImage"
    assert wf["node_count"] >= 1
    assert "KSampler" in wf["node_types"]
    # template registry metadata
    assert wf["template_id"]
    assert wf["active_version_number"] == 1
    assert wf["file_hash"]


def test_workflow_versions_list(client: TestClient) -> None:
    versions = client.get("/api/v1/workflows/default_image_api/versions")
    assert versions.status_code == 200
    rows = versions.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1
    v1 = rows[0]
    assert v1["workflow_id"] == "default_image_api"
    assert v1["version_number"] == 1
    assert v1["status"] == "active"
    assert v1["file_hash"]
    assert v1["file_path"] == "default_image_api.json"


def test_workflow_versions_unknown_workflow_422(client: TestClient) -> None:
    resp = client.get("/api/v1/workflows/does_not_exist/versions")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_versions_present_in_db(session_factory, client: TestClient) -> None:
    """Registration snapshots a WorkflowTemplate + v1 WorkflowVersion row."""
    client.get("/api/v1/workflows")  # trigger registration
    factory, _ = session_factory
    with factory() as session:
        template = session.scalars(select(WorkflowTemplate)).one_or_none()
        assert template is not None
        assert template.workflow_id == "default_image_api"
        versions = session.scalars(
            select(WorkflowVersion).where(WorkflowVersion.template_id == template.id)
        ).all()
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].status == "active"


def test_registration_is_idempotent(client: TestClient) -> None:
    client.get("/api/v1/workflows")  # first registration
    client.get("/api/v1/workflows")  # second — no new versions
    versions = client.get("/api/v1/workflows/default_image_api/versions").json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1


def test_registration_detects_file_change_creates_v2(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    """A changed template file produces a new immutable version (v2) and re-activates it."""
    catalog_dir = tmp_path / "workflows"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    src = settings.workflows_dir / "default_image_api.json"
    raw = json.loads(src.read_text(encoding="utf-8"))
    target = catalog_dir / "default_image_api.json"
    target.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(settings, "workflows_dir", catalog_dir)

    client.get("/api/v1/workflows")
    v1 = client.get("/api/v1/workflows/default_image_api/versions").json()
    assert v1[0]["version_number"] == 1

    # mutate the template content (different hash)
    mutated = dict(raw)
    mutated["__marker"] = {"note": "changed"}
    target.write_text(json.dumps(mutated), encoding="utf-8")

    client.get("/api/v1/workflows")
    versions = client.get("/api/v1/workflows/default_image_api/versions").json()
    assert versions[0]["version_number"] == 2
    assert versions[0]["status"] == "active"
    assert versions[1]["version_number"] == 1
    assert versions[1]["status"] == "superseded"
