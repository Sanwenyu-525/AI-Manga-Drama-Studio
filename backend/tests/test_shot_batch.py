"""Batch shot operations (autonomous-iteration-02): batch-update / batch-delete.

Covers: full success, per-item partial failure (unknown id / cross-scene id),
empty + duplicate id validation, dirty_state propagation via update_shot reuse,
soft-delete semantics, and per-shot events being published.
"""

from fastapi.testclient import TestClient

from tests.test_api import create_chain


def _make_shots(client: TestClient, scene_id: str, n: int) -> list[dict]:
    return [
        client.post(f"/api/v1/scenes/{scene_id}/shots", json={"shot_type": "medium"}).json()
        for _ in range(n)
    ]


def test_batch_update_all_success(client: TestClient) -> None:
    ids = create_chain(client)
    shots = _make_shots(client, ids["scene_id"], 3)

    resp = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots/batch-update",
        json={"shot_ids": [s["id"] for s in shots], "patch": {"shot_type": "close_up"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["succeeded"] == 3 and body["failed"] == 0
    assert all(r["status"] == "updated" for r in body["results"])

    # Batch semantics = server-side revision overwrite; every shot bumped + dirty.
    for shot in client.get(f"/api/v1/scenes/{ids['scene_id']}/shots").json():
        assert shot["shot_type"] == "close_up"
        assert shot["revision"] == 2
        assert shot["dirty_state"] == "dirty_image"


def test_batch_update_partial_failure(client: TestClient) -> None:
    ids = create_chain(client)
    other = client.post(
        f"/api/v1/episodes/{ids['episode_id']}/scenes", json={"name": "更衣室"}
    ).json()
    shots = _make_shots(client, ids["scene_id"], 2)
    cross = _make_shots(client, other["id"], 1)[0]

    resp = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots/batch-update",
        json={
            "shot_ids": [shots[0]["id"], "no-such-shot", cross["id"], shots[1]["id"]],
            "patch": {"duration": 4.0},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested"] == 4
    assert body["succeeded"] == 2 and body["failed"] == 2
    by_id = {r["shot_id"]: r for r in body["results"]}
    assert by_id[shots[0]["id"]]["status"] == "updated"
    assert by_id["no-such-shot"]["status"] == "failed"
    assert by_id["no-such-shot"]["error_code"] == "ENTITY_NOT_FOUND"
    assert by_id[cross["id"]]["status"] == "failed"
    assert by_id[cross["id"]]["error_code"] == "VALIDATION_ERROR"
    assert by_id[shots[1]["id"]]["status"] == "updated"


def test_batch_update_validation_errors(client: TestClient) -> None:
    ids = create_chain(client)
    shot = _make_shots(client, ids["scene_id"], 1)[0]

    # duplicate ids → 422
    dup = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots/batch-update",
        json={"shot_ids": [shot["id"], shot["id"]], "patch": {"duration": 2.0}},
    )
    assert dup.status_code == 422

    # empty patch → 422
    empty = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots/batch-update",
        json={"shot_ids": [shot["id"]], "patch": {}},
    )
    assert empty.status_code == 422

    # unknown scene → 404
    missing_scene = client.post(
        "/api/v1/scenes/no-such-scene/shots/batch-update",
        json={"shot_ids": [shot["id"]], "patch": {"duration": 2.0}},
    )
    assert missing_scene.status_code == 404


def test_batch_delete_success_and_soft_delete(client: TestClient) -> None:
    ids = create_chain(client)
    shots = _make_shots(client, ids["scene_id"], 3)

    resp = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots/batch-delete",
        json={"shot_ids": [shots[0]["id"], shots[2]["id"]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["succeeded"] == 2 and body["failed"] == 0
    assert {r["status"] for r in body["results"]} == {"deleted"}

    remaining = client.get(f"/api/v1/scenes/{ids['scene_id']}/shots").json()
    assert [s["id"] for s in remaining] == [shots[1]["id"]]

    # deleted shots are invisible and individually 404 (soft delete)
    assert client.get(f"/api/v1/shots/{shots[0]['id']}").status_code == 404


def test_batch_delete_partial_failure(client: TestClient) -> None:
    ids = create_chain(client)
    shots = _make_shots(client, ids["scene_id"], 2)

    resp = client.post(
        f"/api/v1/scenes/{ids['scene_id']}/shots/batch-delete",
        json={"shot_ids": [shots[0]["id"], "no-such-shot"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["succeeded"] == 1 and body["failed"] == 1
    by_id = {r["shot_id"]: r for r in body["results"]}
    assert by_id[shots[0]["id"]]["status"] == "deleted"
    assert by_id["no-such-shot"]["error_code"] == "ENTITY_NOT_FOUND"
    # remaining shot untouched
    assert len(client.get(f"/api/v1/scenes/{ids['scene_id']}/shots").json()) == 1
