"""P3 Gate acceptance (mvp-spec §125 Phase 3 / P3-T003/T004/T005 + production loop).

Full closed-loop integration, driving the worker synchronously (TestClient's portal
loop doesn't advance timers, so run_generation is called directly — the same pattern
as test_generation / test_provenance):

- project → episode → scene → shot → prompt v1 → generation (MockImageProvider) →
  Image v1 asset → regenerate → v2 → activate v1 → provenance for v2 asserts
  generation block + inputs (PROMPT_VERSION + SHOT) + outputs + retry chain.
- P3-T003: import an external file → registered project-scope Asset (copy + SHA-256
  checksum + metadata), never a bare filePath; type/size validated (≤50 MB).
- P3-T005: ready asset whose file is deleted → marked missing, record retained.
"""

import asyncio
import hashlib
import time

from fastapi.testclient import TestClient
from PIL import Image

from app.db import session as db_session_module
from app.generations.worker import run_generation
from app.services.asset_service import project_dir


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
    project = client.post("/api/v1/projects", json={"name": "P3Gate"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shot = client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga, sunset port"},
    ).json()
    return shot


def _png_bytes(width: int = 100, height: int = 150) -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 30, 200)).save(buf, "PNG")
    return buf.getvalue()


def _make_import_project(client: TestClient) -> dict:
    return client.post("/api/v1/projects", json={"name": "P3Import"}).json()


def _upload(client: TestClient, project_id: str, content: bytes, filename: str = "photo.png", form: dict | None = None) -> dict:
    fields = {"asset_type": "image"}
    if form:
        fields.update(form)
    return client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": (filename, content, "image/png")},
        data=fields,
    )


# --- P3-T003: import -------------------------------------------------------

def test_asset_import_registers_project_scoped_asset(client: TestClient) -> None:
    project = _make_import_project(client)
    payload = _png_bytes(120, 200)
    resp = _upload(client, project["id"], payload)
    assert resp.status_code == 201
    body = resp.json()

    # structured AssetRead, never a bare filePath
    assert body["project_id"] == project["id"]
    assert body["type"] == "image"
    assert body["source_type"] == "imported"
    assert body["status"] == "ready"
    assert body["file_path"].startswith("imported/")
    assert body["name"].startswith(f"{project['id']}_IMP_")
    assert body["file_size"] == len(payload)
    assert body["width"] == 120
    assert body["height"] == 200
    assert body["mime_type"] == "image/png"
    assert len(body["checksum"]) == 64
    # no shot / version group ownership for imported assets
    assert body["version_group_id"] is None
    assert body["version_number"] is None
    assert body["generation_id"] is None

    # checksum matches the uploaded bytes (SHA-256 reuse)
    assert body["checksum"] == hashlib.sha256(payload).hexdigest()

    # the file actually exists inside the project directory
    disk = project_dir(body["project_id"]) / body["file_path"]
    assert disk.is_file()
    assert disk.read_bytes() == payload

    # content endpoint serves it back
    content = client.get(f"/api/v1/assets/{body['id']}/content")
    assert content.status_code == 200
    assert content.content == payload


def test_asset_import_rejects_invalid_type(client: TestClient) -> None:
    project = _make_import_project(client)
    resp = _upload(client, project["id"], _png_bytes(), form={"asset_type": "audio"})
    assert resp.status_code == 422


# --- P3-T005: missing detection -------------------------------------------

def test_missing_detection_marks_ready_as_missing_keeps_record(client: TestClient) -> None:
    project = _make_import_project(client)
    body = _upload(client, project["id"], _png_bytes()).json()
    assert body["status"] == "ready"

    # no deletions yet → scan finds nothing missing
    scan0 = client.post(f"/api/v1/projects/{project['id']}/assets/check-missing").json()
    assert scan0 == {"checked": 1, "missing": 0}

    # delete the physical file (simulates loss / manual move)
    disk = project_dir(project["id"]) / body["file_path"]
    assert disk.exists()
    disk.unlink()

    scan = client.post(f"/api/v1/projects/{project['id']}/assets/check-missing").json()
    assert scan == {"checked": 1, "missing": 1}

    # record is RETAINED (not deleted) and now flagged missing
    with db_session_module.session_factory_provider()() as s:
        from app.db.models import Asset

        row = s.get(Asset, body["id"])
        assert row is not None
        assert row.status == "missing"
        assert row.deleted_at is None

    # second scan is stable: already-missing rows are not re-counted as newly missing
    scan2 = client.post(f"/api/v1/projects/{project['id']}/assets/check-missing").json()
    assert scan2 == {"checked": 0, "missing": 0}


# --- P3 gate: full production loop → provenance -----------------------------

def test_gate_generation_to_provenance_closed_loop(client: TestClient) -> None:
    shot = _make_shot(client)

    # create prompt v1 and activate it for the shot
    ver = client.post(
        f"/api/v1/shots/{shot['id']}/prompts",
        json={"prompt_type": "SHOT_IMAGE", "positive_prompt": "manga, port at dusk"},
    ).json()

    # generation #1 → Image V1
    g1 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    assert g1.status_code == 202
    g1 = _wait_status(client, g1.json()["id"])
    assert g1["status"] == "completed"
    v1_asset_id = g1["output_asset_id"]

    # regenerate → Image V2 (V1 preserved)
    g2 = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"})
    g2 = _wait_status(client, g2.json()["id"])
    assert g2["status"] == "completed"
    v2_asset_id = g2["output_asset_id"]
    assert v2_asset_id != v1_asset_id

    versions = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    by_number = {v["version_number"]: v for v in versions}
    assert by_number[1]["asset_id"] == v1_asset_id
    assert by_number[2]["asset_id"] == v2_asset_id
    assert by_number[2]["is_active"] is True  # newest active
    assert by_number[1]["is_active"] is False

    # activate V1 as the shot's active image
    activated = client.post(f"/api/v1/shots/{shot['id']}/image-versions/{v1_asset_id}/activate").json()
    assert activated["is_active"] is True
    versions_after = client.get(f"/api/v1/shots/{shot['id']}/versions").json()
    active_after = {v["version_number"]: v["is_active"] for v in versions_after}
    assert active_after[1] is True
    assert active_after[2] is False

    # provenance for the V2 asset: generation block + inputs + output + retry chain
    prov = client.get(f"/api/v1/assets/{v2_asset_id}/provenance").json()
    assert prov["asset"]["id"] == v2_asset_id

    gen = prov["generation"]
    assert gen is not None
    assert gen["id"] == g2["id"]
    assert gen["type"] == "image"
    assert gen["provider"] == "mock"
    assert gen["prompt_version_id"] == ver["id"]
    assert gen["status"] == "completed"

    # inputs: PROMPT_VERSION (the prompt v1) + SHOT
    input_types = {i["reference_type"]: i for i in prov["inputs"]}
    assert "PROMPT_VERSION" in input_types
    assert input_types["PROMPT_VERSION"]["reference_id"] == ver["id"]
    assert "SHOT" in input_types
    assert input_types["SHOT"]["reference_id"] == shot["id"]

    # outputs are queryable for the producing generation
    outputs = client.get(f"/api/v1/generations/{g2['id']}/outputs").json()
    assert len(outputs["outputs"]) == 1
    assert outputs["outputs"][0]["asset_id"] == v2_asset_id

    # retry chain: g2 is a fresh generation (not a retry of g1), no ancestors
    assert prov["retry_of"] is None
    assert prov["ancestors"] == []

    # retry g2 → a new chained generation
    retried = client.post(f"/api/v1/generations/{g2['id']}/retry")
    assert retried.status_code == 202
    g3 = _wait_status(client, retried.json()["id"])
    assert g3["status"] == "completed"
    assert g3["retry_of"] == g2["id"]

    prov_retry = client.get(f"/api/v1/assets/{g3['output_asset_id']}/provenance").json()
    assert prov_retry["retry_of"] == g2["id"]
    assert g2["id"] in prov_retry["ancestors"]
