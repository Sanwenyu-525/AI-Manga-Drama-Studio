"""P3-T012/T013 provenance tests: generation_inputs/outputs + asset provenance API.

Scenarios:
1. After a generation completes, /generations/{id}/outputs returns the produced asset.
2. /assets/{id}/provenance exposes provider/model/prompt_version_id and inputs
   (PROMPT_VERSION + SHOT) for a generation that consumed a prompt version.
3. Retrying chains via retry_of: the retry generation's provenance reports
   retry_of and the ancestors (retry chain) is queryable.
"""

import asyncio
import time

from fastapi.testclient import TestClient

from app.generations.worker import run_generation


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _wait_status(client: TestClient, generation_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gen = client.get(f"/api/v1/generations/{generation_id}").json()
        if gen["status"] in ("completed", "failed", "cancelled"):
            return gen
        time.sleep(0.05)
    raise TimeoutError(f"generation {generation_id} did not finish in {timeout}s")


def _make_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "Provenance"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}
    ).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga style, sunset alley"},
    ).json()
    return shot


def _make_versioned_shot(client: TestClient) -> tuple[dict, dict]:
    """Shot with an active SHOT_IMAGE prompt version; returns (shot, version)."""
    shot = _make_shot(client)
    ver = client.post(
        f"/api/v1/shots/{shot['id']}/prompts",
        json={"prompt_type": "SHOT_IMAGE", "positive_prompt": "manga style, neon street"},
    ).json()
    assert ver["is_active"] is True
    return shot, ver


def _complete(client: TestClient, shot_id: str) -> dict:
    """Create a generation and drive it to completion; returns the completed generation."""
    created = client.post(f"/api/v1/shots/{shot_id}/generations", json={"type": "image"})
    assert created.status_code == 202
    return _drive_to_complete(client, created.json()["id"])


def _drive_to_complete(client: TestClient, generation_id: str) -> dict:
    """Drive an existing (already created) generation to completion."""
    _drive(generation_id)
    done = _wait_status(client, generation_id)
    assert done["status"] == "completed", done.get("error_message")
    return done


# --- scenario 1: outputs after completion -------------------------------

def test_generation_outputs_after_completion(client: TestClient) -> None:
    shot = _make_shot(client)
    done = _complete(client, shot["id"])

    outputs = client.get(f"/api/v1/generations/{done['id']}/outputs")
    assert outputs.status_code == 200
    body = outputs.json()
    assert body["generation_id"] == done["id"]
    assert len(body["outputs"]) == 1
    out = body["outputs"][0]
    assert out["asset_id"] == done["output_asset_id"]
    assert out["role"] == "primary"
    assert out["type"] == "image"
    assert out["status"] == "ready"


# --- scenario 2: asset provenance ---------------------------------------

def test_asset_provenance_includes_generation_and_inputs(client: TestClient) -> None:
    shot, ver = _make_versioned_shot(client)
    done = _complete(client, shot["id"])

    provenance = client.get(f"/api/v1/assets/{done['output_asset_id']}/provenance")
    assert provenance.status_code == 200
    body = provenance.json()

    # asset summary round-trips
    assert body["asset"]["id"] == done["output_asset_id"]
    assert body["asset"]["type"] == "image"

    # generation block carries the expected provenance fields
    gen = body["generation"]
    assert gen is not None
    assert gen["id"] == done["id"]
    assert gen["type"] == "image"
    assert gen["provider"] == "mock"
    assert gen["model"] is None
    assert gen["prompt_version_id"] == ver["id"]
    assert gen["status"] == "completed"
    assert gen["completed_at"] is not None
    assert gen["parameters"] is not None

    # inputs include PROMPT_VERSION + SHOT
    types = {i["reference_type"] for i in body["inputs"]}
    assert "SHOT" in types
    assert "PROMPT_VERSION" in types
    prompt_input = next(i for i in body["inputs"] if i["reference_type"] == "PROMPT_VERSION")
    assert prompt_input["reference_id"] == ver["id"]
    shot_input = next(i for i in body["inputs"] if i["reference_type"] == "SHOT")
    assert shot_input["reference_id"] == shot["id"]


def test_generation_inputs_endpoint(client: TestClient) -> None:
    shot = _make_shot(client)
    created = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    _drive(created.json()["id"])
    _wait_status(client, created.json()["id"])

    resp = client.get(f"/api/v1/generations/{created.json()['id']}/inputs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["generation_id"] == created.json()["id"]
    types = {i["reference_type"] for i in body["inputs"]}
    assert "SHOT" in types


# --- scenario 3: retry chain --------------------------------------------

def test_retry_chain_provenance(client: TestClient) -> None:
    shot, ver = _make_versioned_shot(client)
    g1 = _complete(client, shot["id"])

    retried = client.post(f"/api/v1/generations/{g1['id']}/retry")
    assert retried.status_code == 202
    g2 = _drive_to_complete(client, retried.json()["id"])
    assert g2["retry_of"] == g1["id"]

    # new generation's provenance is a separate asset
    assert g2["output_asset_id"] != g1["output_asset_id"]

    # asset provenance for the retry asset exposes the chain
    prov2 = client.get(f"/api/v1/assets/{g2['output_asset_id']}/provenance").json()
    assert prov2["retry_of"] == g1["id"]
    assert g1["id"] in prov2["ancestors"]
    # both generations consumed the same prompt version
    gen2 = prov2["generation"]
    assert gen2["id"] == g2["id"]
    assert gen2["prompt_version_id"] == ver["id"]

    # the original generation's provenance has no ancestors
    prov1 = client.get(f"/api/v1/assets/{g1['output_asset_id']}/provenance").json()
    assert prov1["retry_of"] is None
    assert prov1["ancestors"] == []


# --- edge: missing asset / not found ------------------------------------

def test_provenance_404_for_unknown_asset(client: TestClient) -> None:
    resp = client.get("/api/v1/assets/does-not-exist/provenance")
    assert resp.status_code == 404
