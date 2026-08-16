"""P6-B Asset Browser API (Asset Browser 后端缺口补全).

Covers the two new endpoints:
  GET /api/v1/projects/{project_id}/assets   — {total, items} paginated + filtered list
  GET /api/v1/assets/{asset_id}              — single-asset detail (Inspector)

Verified: pagination, type/status filters + 422 on invalid filter, 404 on missing /
soft-deleted asset, detail field completeness (checksum/file_size/version refs), soft-delete
exclusion from the list, and cross-project isolation.
"""

import asyncio
import hashlib
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.db import session as db_session_module
from app.db.models import Asset
from app.generations.worker import run_generation


def _png(payload: bytes | None = None, width: int = 120, height: int = 80) -> bytes:
    if payload is None:
        buf = io.BytesIO()
        Image.new("RGB", (width, height), (200, 80, 40)).save(buf, "PNG")
        return buf.getvalue()
    return payload


def _make_project(client: TestClient, name: str = "P6BAssets") -> dict:
    return client.post("/api/v1/projects", json={"name": name}).json()


def _upload(client: TestClient, project_id: str, content: bytes, filename: str = "img.png", asset_type: str = "image") -> dict:
    return client.post(
        f"/api/v1/projects/{project_id}/assets/import",
        files={"file": (filename, content, "image/png")},
        data={"asset_type": asset_type},
    ).json()


def _drive(generation_id: str) -> None:
    asyncio.run(run_generation(generation_id))


def _make_shot(client: TestClient, project_id: str) -> dict:
    episode = client.post(f"/api/v1/projects/{project_id}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    return client.post(
        f"/api/v1/scenes/{scene['id']}/shots",
        json={"shot_type": "medium", "image_prompt": "manga, street"},
    ).json()


# --- list: pagination + shape ---------------------------------------------

def test_list_project_assets_paginated_shape(client: TestClient) -> None:
    project = _make_project(client)
    a1 = _upload(client, project["id"], _png(), filename="a.png")
    _upload(client, project["id"], _png(), filename="b.png")
    _upload(client, project["id"], _png(), filename="c.png")

    resp = client.get(f"/api/v1/projects/{project['id']}/assets")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3

    # newest first (created_at desc) → the first import is the oldest => last
    ids = [it["id"] for it in body["items"]]
    assert len(set(ids)) == 3
    assert ids[-1] == a1["id"]  # first import = newest => first; oldest => last

    # each item carries the P6-B field set
    item = body["items"][0]
    for key in (
        "id", "type", "status", "version_group_id", "version_number",
        "checksum", "file_size", "width", "height", "created_at", "file_path", "thumbnail_url",
    ):
        assert key in item, f"missing list field {key}"


def test_list_pagination_offset_limit(client: TestClient) -> None:
    project = _make_project(client)
    for i in range(5):
        _upload(client, project["id"], _png(), filename=f"f{i}.png")

    page = client.get(f"/api/v1/projects/{project['id']}/assets", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 5
    assert len(page["items"]) == 2

    all_items = client.get(f"/api/v1/projects/{project['id']}/assets").json()["items"]
    assert [it["id"] for it in page["items"]] == [it["id"] for it in all_items[1:3]]


def test_list_limit_clamped_422(client: TestClient) -> None:
    project = _make_project(client)
    _upload(client, project["id"], _png())
    # limit > 200 → 422 (FastAPI Query le=200)
    assert client.get(f"/api/v1/projects/{project['id']}/assets", params={"limit": 201}).status_code == 422
    # negative offset → 422
    assert client.get(f"/api/v1/projects/{project['id']}/assets", params={"offset": -1}).status_code == 422


# --- list: filters + validation ------------------------------------------

def test_list_asset_type_filter(client: TestClient) -> None:
    project = _make_project(client)
    _upload(client, project["id"], _png(), filename="img.png")  # image
    resp = client.get(f"/api/v1/projects/{project['id']}/assets", params={"asset_type": "image"})
    body = resp.json()
    assert body["total"] == 1
    assert all(it["type"] == "image" for it in body["items"])


def test_list_invalid_asset_type_422(client: TestClient) -> None:
    project = _make_project(client)
    _upload(client, project["id"], _png())
    resp = client.get(f"/api/v1/projects/{project['id']}/assets", params={"asset_type": "bogus"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_status_filter(client: TestClient) -> None:
    project = _make_project(client)
    good = _upload(client, project["id"], _png())
    # flip one asset to 'missing' via direct session
    with db_session_module.session_factory_provider()() as s:
        row = s.get(Asset, good["id"])
        row.status = "missing"
        s.commit()

    missing = client.get(f"/api/v1/projects/{project['id']}/assets", params={"status": "missing"}).json()
    assert missing["total"] == 1
    assert missing["items"][0]["id"] == good["id"]

    ready = client.get(f"/api/v1/projects/{project['id']}/assets", params={"status": "ready"}).json()
    assert ready["total"] == 0


def test_list_invalid_status_422(client: TestClient) -> None:
    project = _make_project(client)
    _upload(client, project["id"], _png())
    resp = client.get(f"/api/v1/projects/{project['id']}/assets", params={"status": "nonsense"})
    assert resp.status_code == 422


def test_list_project_404(client: TestClient) -> None:
    assert client.get("/api/v1/projects/does-not-exist/assets").status_code == 404


# --- soft-delete + isolation ---------------------------------------------

def test_list_excludes_soft_deleted(client: TestClient) -> None:
    project = _make_project(client)
    a = _upload(client, project["id"], _png())
    _upload(client, project["id"], _png())

    with db_session_module.session_factory_provider()() as s:
        row = s.get(Asset, a["id"])
        row.deleted_at = "2026-01-01T00:00:00Z"
        s.commit()

    body = client.get(f"/api/v1/projects/{project['id']}/assets").json()
    assert body["total"] == 1
    assert all(it["id"] != a["id"] for it in body["items"])

    # include_deleted=true brings it back
    body_incl = client.get(
        f"/api/v1/projects/{project['id']}/assets", params={"include_deleted": "true"}
    ).json()
    assert body_incl["total"] == 2


def test_cross_project_isolation(client: TestClient) -> None:
    pA = _make_project(client, "ProjA")
    pB = _make_project(client, "ProjB")
    aA = _upload(client, pA["id"], _png(), filename="shared.png")
    aB = _upload(client, pB["id"], _png(), filename="shared.png")

    listA = client.get(f"/api/v1/projects/{pA['id']}/assets").json()["items"]
    listB = client.get(f"/api/v1/projects/{pB['id']}/assets").json()["items"]
    idsA = {it["id"] for it in listA}
    idsB = {it["id"] for it in listB}
    assert aA["id"] in idsA and aB["id"] in idsB
    assert idsA.isdisjoint(idsB)


# --- detail ---------------------------------------------------------------

def test_get_asset_detail_full_fields(client: TestClient) -> None:
    project = _make_project(client)
    payload = _png()
    uploaded = _upload(client, project["id"], payload, filename="detail.png")

    detail = client.get(f"/api/v1/assets/{uploaded['id']}").json()
    assert detail["id"] == uploaded["id"]
    assert detail["project_id"] == project["id"]
    assert detail["type"] == "image"
    assert detail["checksum"] == hashlib.sha256(payload).hexdigest()
    assert detail["file_size"] == len(payload)
    assert detail["width"] == 120
    assert detail["height"] == 80
    assert detail["file_path"].startswith("imported/")
    assert detail["thumbnail_url"] == f"/api/v1/assets/{uploaded['id']}/thumbnail"
    # imported asset: no version-group / provenance refs
    assert detail["version_group_id"] is None
    assert detail["version_number"] is None
    assert detail["generation_id"] is None
    assert detail["parent_asset_id"] is None
    assert detail["shot_id"] is None
    assert detail["meta_json"] is not None


def test_get_asset_detail_generated_version_refs(client: TestClient) -> None:
    # A generated shot asset carries version_group_id/version_number/generation_id
    # and a shot_id reference summary.
    project = _make_project(client)
    shot = _make_shot(client, project["id"])
    g = client.post(f"/api/v1/shots/{shot['id']}/generations", json={"type": "image"}).json()
    _drive(g["id"])
    done = client.get(f"/api/v1/generations/{g['id']}").json()
    assert done["status"] == "completed"
    asset_id = done["output_asset_id"]

    detail = client.get(f"/api/v1/assets/{asset_id}").json()
    assert detail["version_group_id"].startswith("vg:shot:")
    assert detail["version_number"] == 1
    assert detail["generation_id"] == g["id"]
    assert detail["shot_id"] == shot["id"]
    assert detail["checksum"]
    assert detail["file_size"] is not None
    assert detail["thumbnail_url"] == f"/api/v1/assets/{asset_id}/thumbnail"


def test_get_asset_detail_404(client: TestClient) -> None:
    assert client.get("/api/v1/assets/does-not-exist").status_code == 404


def test_get_asset_detail_404_soft_deleted(client: TestClient) -> None:
    project = _make_project(client)
    a = _upload(client, project["id"], _png())
    with db_session_module.session_factory_provider()() as s:
        s.get(Asset, a["id"]).deleted_at = "2026-01-01T00:00:00Z"
        s.commit()
    assert client.get(f"/api/v1/assets/{a['id']}").status_code == 404
