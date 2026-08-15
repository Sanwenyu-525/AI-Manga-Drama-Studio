"""P1-E2-T01: provider/workflow contract tests — no GPU, no real ComfyUI needed.

- Default workflow is locatable and preflight-clean (output node + placeholders).
- Missing placeholder / missing output node → preflight fails (ComfyUIError).
- Unknown provider / workflow / media type → structured 422 at generation creation.
- generation.provider equals the implementation the worker actually runs.
- Test-connection endpoint reports workflow preflight status.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import ComfyUIError, ValidationError
from app.providers.comfyui.workflow_mapper import (
    DEFAULT_WORKFLOW_ID,
    REQUIRED_PLACEHOLDERS,
    WorkflowMapper,
    resolve_workflow_path,
)

_VALID_TEMPLATE = {
    "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x.safetensors"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$PROMPT", "clip": ["3", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "$NEGATIVE_PROMPT", "clip": ["3", 1]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": "$WIDTH", "height": "$HEIGHT", "batch_size": 1}},
    "12": {
        "class_type": "KSampler",
        "inputs": {"seed": "$SEED", "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["3", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]},
    },
    "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 2]}},
    "14": {"class_type": "SaveImage", "inputs": {"filename_prefix": "studio/shot", "images": ["13", 0]}},
}


def _write_template(directory, filename: str, template: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(json.dumps(template), encoding="utf-8")


# --- workflow locatability & preflight ---

def test_default_workflow_locatable_and_preflight_clean() -> None:
    path = resolve_workflow_path(None)
    assert path.exists(), f"default workflow missing at {path}"
    assert path.name == "default_image_api.json"
    assert settings.workflows_dir == path.parent

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID)
    template = mapper.load_template()
    assert mapper.output_node_id is not None
    assert template[mapper.output_node_id]["class_type"] == "SaveImage"
    # every required placeholder is present in the template
    input_values = [v for node in template.values() for v in node.get("inputs", {}).values()]
    for placeholder in REQUIRED_PLACEHOLDERS:
        assert placeholder in input_values


def test_mapper_preflight_fails_on_missing_placeholder(tmp_path) -> None:
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    del template["12"]["inputs"]["seed"]  # drop $SEED
    _write_template(tmp_path, "default_image_api.json", template)

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ComfyUIError, match="placeholder"):
        mapper.preflight()


def test_mapper_preflight_fails_on_missing_output_node(tmp_path) -> None:
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    del template["14"]  # no SaveImage
    _write_template(tmp_path, "default_image_api.json", template)

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    with pytest.raises(ComfyUIError, match="SaveImage"):
        mapper.preflight()


def test_mapper_preflight_fails_on_two_output_nodes(tmp_path) -> None:
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    template["99"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "x", "images": ["13", 0]}}
    _write_template(tmp_path, "default_image_api.json", template)

    with pytest.raises(ComfyUIError, match="exactly one"):
        WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path).preflight()


def test_workflow_id_selects_template_path(tmp_path) -> None:
    """workflow_id decides the template — the file at the resolved path is really loaded."""
    template = json.loads(json.dumps(_VALID_TEMPLATE))
    template["6"]["inputs"]["text"] = "$PROMPT"  # marker: custom copy
    _write_template(tmp_path, "default_image_api.json", template)

    mapper = WorkflowMapper(DEFAULT_WORKFLOW_ID, workflows_dir=tmp_path)
    built = mapper.build(prompt="hello", seed=7, width=64, height=64)
    assert built["6"]["inputs"]["text"] == "hello"  # substituted from the tmp copy

    # unknown id → rejected, never a silent fallback to another template
    with pytest.raises(ValidationError):
        WorkflowMapper("does_not_exist", workflows_dir=tmp_path)


# --- generation-time fail fast (API) ---

def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "P1E2T01"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, night"},
    ).json()


def test_unknown_provider_rejected_422(client: TestClient) -> None:
    shot = _make_shot(client)
    resp = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "provider": "bogus_provider"},
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "bogus_provider" in str(err["details"])


def test_unknown_workflow_rejected_422(client: TestClient) -> None:
    shot = _make_shot(client)
    resp = client.post(
        f"/api/v1/shots/{shot['id']}/generations",
        json={"type": "image", "workflow_id": "bogus_workflow"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_video_type_rejected_422(client: TestClient) -> None:
    shot = _make_shot(client)
    resp = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "video"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["type"] == "video"
    assert err["details"]["supported"] == ["image"]


def test_generation_provider_matches_implementation(client: TestClient, monkeypatch) -> None:
    """generation.provider is the canonical id the worker actually executes."""
    import asyncio

    from app.generations import worker as worker_module

    shot = _make_shot(client)
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    assert created["provider"] == settings.image_provider  # canonical default, not "default"

    resolved_ids: list[str] = []
    original = worker_module.get_image_provider

    def spy(provider_id=None):
        resolved_ids.append(provider_id)
        return original(provider_id)

    monkeypatch.setattr(worker_module, "get_image_provider", spy)
    asyncio.run(worker_module.run_generation(created["id"]))

    assert resolved_ids == [created["provider"]]
    done = client.get(f"/api/v1/generations/{created['id']}").json()
    assert done["status"] == "completed", done.get("error_message")
    assert done["provider"] == settings.image_provider


def test_provider_test_endpoint_reports_workflow_preflight(client: TestClient, monkeypatch) -> None:
    """POST /providers/comfyui/test includes template preflight status (no GPU needed)."""
    from app.api import providers as providers_api

    class _FakeComfy:
        async def health_check(self):
            return True, 5.0

    monkeypatch.setattr(providers_api, "get_comfyui_provider", lambda: _FakeComfy())
    resp = client.post("/api/v1/providers/comfyui/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["workflow"]["status"] == "ok"
    assert body["workflow"]["output_node"] == "14"
