"""P1-E1-T02: DB invariants — atomic revision, safe reorder, unique constraints,
soft-delete parent/child visibility, legacy duplicate detection.

Regression focus:
- Two writers with the same stale revision: exactly one wins (409 for the loser).
- Partial / duplicate / cross-scene reorder is rejected with data unchanged.
- Unique partial indexes (live rows only) exist and reject bypass writes.
- Children of soft-deleted parents are hidden for read AND write.
- The invariants migration detects legacy duplicates instead of dropping them.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError, ValidationError
from app.db.models import Scene
from app.domain.episode import EpisodeCreate
from app.domain.project import ProjectCreate
from app.domain.scene import SceneCreate
from app.domain.shot import ShotCreate, ShotUpdate
from app.services import (
    CharacterService,
    EpisodeService,
    ProjectService,
    SceneService,
    ShotService,
)


def _chain(session_factory):
    factory, _ = session_factory
    session = factory()
    project = ProjectService(session).create_project(ProjectCreate(name="INV"))
    episode = EpisodeService(session).create_episode(project.id, EpisodeCreate(title="E1"))
    scene = SceneService(session).create_scene(episode.id, SceneCreate(name="S1"))
    return session, project, episode, scene


# --- atomic revision (lost-update protection) ---

def test_two_writers_same_revision_shot_only_one_wins(session_factory) -> None:
    session, _, _, scene = _chain(session_factory)
    shot = ShotService(session).create_shot(scene.id, ShotCreate(shot_type="medium"))
    shot_id = shot.id
    session.close()

    factory, _ = session_factory
    stale = factory()
    fresh = factory()
    stale_shot = ShotService(stale)
    fresh_shot = ShotService(fresh)

    # both writers load revision 1
    assert stale_shot.get_shot(shot_id).revision == 1
    assert fresh_shot.get_shot(shot_id).revision == 1

    # writer B commits first…
    fresh_shot.update_shot(shot_id, 1, ShotUpdate(emotion="tense"))
    # …writer A's stale revision must fail at the DB level (not a silent overwrite)
    with pytest.raises(ConflictError):
        stale_shot.update_shot(shot_id, 1, ShotUpdate(emotion="calm"))

    # B's change is the survivor; A's write never landed
    final = fresh_shot.get_shot(shot_id)
    assert final.revision == 2
    assert final.emotion == "tense"
    stale.close()
    fresh.close()


def test_two_writers_same_revision_character_only_one_wins(session_factory) -> None:
    from app.domain.character import CharacterCreate, CharacterUpdate

    session, project, _, _ = _chain(session_factory)
    character = CharacterService(session).create_character(
        project.id, CharacterCreate(name="顾言")
    )
    character_id = character.id
    session.close()

    factory, _ = session_factory
    stale = factory()
    fresh = factory()
    stale_char = CharacterService(stale)
    fresh_char = CharacterService(fresh)

    assert stale_char.get_character(character_id).revision == 1
    assert fresh_char.get_character(character_id).revision == 1

    fresh_char.update_character(character_id, 1, CharacterUpdate(alias="阿言"))
    with pytest.raises(ConflictError):
        stale_char.update_character(character_id, 1, CharacterUpdate(gender="male"))

    final = fresh_char.get_character(character_id)
    assert final.revision == 2
    assert final.alias == "阿言"  # fresh writer's change survived
    stale.close()
    fresh.close()


# --- safe reorder ---

def test_reorder_rejects_partial_ids(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "RE"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S"}).json()
    s1 = client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "wide"}).json()
    s2 = client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "medium"}).json()
    s3 = client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "close_up"}).json()

    # partial list → rejected, data unchanged
    resp = client.patch(
        f"/api/v1/scenes/{scene['id']}/shots/reorder",
        json=[s3["id"], s1["id"]],
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # duplicate ids → rejected
    resp = client.patch(
        f"/api/v1/scenes/{scene['id']}/shots/reorder",
        json=[s3["id"], s3["id"], s1["id"], s2["id"]],
    )
    assert resp.status_code == 422

    # cross-scene id → rejected
    other_scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S2"}).json()
    foreign = client.post(f"/api/v1/scenes/{other_scene['id']}/shots", json={"shot_type": "full"}).json()
    resp = client.patch(
        f"/api/v1/scenes/{scene['id']}/shots/reorder",
        json=[s1["id"], s2["id"], s3["id"], foreign["id"]],
    )
    assert resp.status_code == 422

    # data unchanged after all rejections
    shots = client.get(f"/api/v1/scenes/{scene['id']}/shots").json()
    assert [s["shot_number"] for s in shots] == [1, 2, 3]
    assert [s["id"] for s in shots] == [s1["id"], s2["id"], s3["id"]]


def test_reorder_swaps_orders_within_unique_constraints(client: TestClient) -> None:
    """Full reversal exercises the two-phase numbering (unique shot_order index)."""
    project = client.post("/api/v1/projects", json={"name": "RE2"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S"}).json()
    shots = [
        client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "wide"}).json(),
        client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "medium"}).json(),
        client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "close_up"}).json(),
        client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "full"}).json(),
    ]
    reversed_ids = [s["id"] for s in reversed(shots)]

    reordered = client.patch(
        f"/api/v1/scenes/{scene['id']}/shots/reorder",
        json=reversed_ids,
    )
    assert reordered.status_code == 200
    body = reordered.json()
    assert [s["id"] for s in body] == reversed_ids
    assert [s["shot_number"] for s in body] == [1, 2, 3, 4]


# --- unique constraints ---

def test_unique_scene_number_per_episode_enforced(session_factory) -> None:
    session, _, episode, _ = _chain(session_factory)
    session.add(Scene(episode_id=episode.id, scene_number=5, name="A", status="draft"))
    session.add(Scene(episode_id=episode.id, scene_number=5, name="B", status="draft"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_unique_shot_characters_pair_enforced(session_factory) -> None:
    session, project, episode, scene = _chain(session_factory)
    from app.domain.character import CharacterCreate

    character = CharacterService(session).create_character(project.id, CharacterCreate(name="C"))
    from app.domain.shot import ShotCreate

    # duplicate character ids in one request → ValidationError (not a DB 500)
    with pytest.raises(ValidationError):
        ShotService(session).create_shot(
            scene.id, ShotCreate(shot_type="medium", character_ids=[character.id, character.id])
        )
    session.close()


def test_unique_shots_per_scene_number_soft_delete_reuse(session_factory) -> None:
    """Partial unique index: soft-deleted rows don't block number reuse."""
    session, _, _, scene = _chain(session_factory)
    service = ShotService(session)
    s1 = service.create_shot(scene.id, ShotCreate(shot_type="wide"))
    service.delete_shot(s1.id)
    s2 = service.create_shot(scene.id, ShotCreate(shot_type="medium"))
    assert s2.shot_number == 1  # number reused after soft delete
    session.close()


# --- soft-delete parent/child visibility ---

def test_children_hidden_after_parent_scene_delete(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "SD"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S"}).json()
    shot = client.post(f"/api/v1/scenes/{scene['id']}/shots", json={"shot_type": "medium"}).json()

    client.delete(f"/api/v1/scenes/{scene['id']}")

    # children are hidden for read AND write (404, not orphaned visibility)
    assert client.get(f"/api/v1/shots/{shot['id']}").status_code == 404
    assert client.get(f"/api/v1/scenes/{scene['id']}/shots").status_code == 404
    assert client.get(f"/api/v1/scenes/{scene['id']}/storyboard").status_code == 404
    patch = client.patch(
        f"/api/v1/shots/{shot['id']}",
        json={"revision": 1, "patch": {"shot_type": "close_up"}},
    )
    assert patch.status_code == 404
    assert client.delete(f"/api/v1/shots/{shot['id']}").status_code == 404

    # the shot row still exists (soft delete only) — restore semantics preserved;
    # a restored scene would make its children visible again (rows were not deleted)


# --- legacy duplicate detection ---

def test_migration_duplicate_detector_rejects_duplicates() -> None:
    import importlib.util
    from pathlib import Path

    from sqlalchemy import create_engine

    migration_path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "b1e2f3a4c5d6_p1_e1_t02_invariants.py"
    spec = importlib.util.spec_from_file_location("invariants_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _assert_no_legacy_duplicates = module._assert_no_legacy_duplicates

    import sqlalchemy as sa

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE scenes (id TEXT PRIMARY KEY, episode_id TEXT, scene_number INT, deleted_at TEXT)"))
        conn.execute(sa.text("CREATE TABLE shots (id TEXT PRIMARY KEY, scene_id TEXT, shot_number INT, shot_order INT, deleted_at TEXT)"))
        conn.execute(sa.text("CREATE TABLE shot_characters (id TEXT PRIMARY KEY, shot_id TEXT, character_id TEXT)"))
        conn.execute(sa.text("CREATE TABLE media_versions (id TEXT PRIMARY KEY, shot_id TEXT, media_type TEXT, version_number INT, is_active INT)"))
        conn.execute(sa.text("INSERT INTO scenes VALUES ('a', 'e1', 1, NULL), ('b', 'e1', 1, NULL)"))  # duplicate
        with pytest.raises(RuntimeError, match="legacy duplicates"):
            _assert_no_legacy_duplicates(conn)
    engine.dispose()
