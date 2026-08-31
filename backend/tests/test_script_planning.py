"""Stage B tests: novel → analyze → scenes → generate-shots → storyboard (mvp-spec §62).

P1-E1-T01 (修复 AI 计划映射与批量写入事务):
- ScenePlan title/location/time are persisted (mapped, not silently dropped).
- Repeating the same confirm request is idempotent — no duplicate Scenes/Shots.
- New input replaces previous AI-created rows; manual rows are preserved.
- A failure mid-batch rolls back everything (all-or-nothing).

Uses FakeLLMGateway (default STUDIO_LLM_MODE=fake) so the full AI chain runs keyless.
"""

import time

from fastapi.testclient import TestClient

NOVEL_TEXT = (
    "夜色降临，城市的天台上一群人围坐在一起。沈亦站在栏杆边，手里攥着一颗篮球。"
    "顾言从楼梯口走上来，神色复杂地看着他。'你真的决定了吗？'顾言问。"
    "沈亦没有回头，只是把篮球抛向空中又接住。'最后一种打法，要么赢，要么散。'\n"
    "第二天，学校体育馆里人声鼎沸。决赛的哨声响起，沈亦带球突破，顾言在三分线外等待。"
    "观众席上，教练紧握拳头。比赛还剩十秒，比分胶着，沈亦起跳投篮，篮球在空中划出一道弧线。\n"
    "球进了。体育馆爆发出山呼海啸般的欢呼。沈亦瘫坐在地上，眼眶泛红。"
    "顾言跑过来一把拉起他，'赢了！'沈亦笑着摇头，'这只是开始。'\n"
    "深夜，空无一人的球场上，沈亦独自练习。灯光下他的影子拉得很长。"
    "手机亮起，一条消息：'明天见。'他盯着屏幕看了很久，最终没有回复，只是继续投篮。\n"
    "一周后，城市的地下停车场，一场不为人知的比赛即将开始。沈亦换上了黑色的队服，"
    "对手是曾经打败过他的老对手。他深吸一口气，走进灯光之中。"
)


def create_episode_with_source(client: TestClient) -> tuple[str, str]:
    project = client.post("/api/v1/projects", json={"name": "StageB 验收"}).json()
    episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes",
        json={"title": "第一集", "source_text": NOVEL_TEXT},
    ).json()
    return project["id"], episode["id"]


def _wait_operation(client: TestClient, op_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        op = client.get(f"/api/v1/operations/{op_id}").json()
        if op["status"] in ("completed", "failed"):
            return op
        time.sleep(0.05)
    raise TimeoutError(f"operation {op_id} did not finish in {timeout}s")


def _analyze(client: TestClient, episode_id: str) -> dict:
    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    assert resp.status_code == 202
    return _wait_operation(client, resp.json()["operation_id"])


def _generate_shots(client: TestClient, scene_id: str) -> dict:
    resp = client.post(f"/api/v1/scenes/{scene_id}/generate-shots")
    assert resp.status_code == 202
    return _wait_operation(client, resp.json()["operation_id"])


def _first_scene(client: TestClient, episode_id: str, timeout: float = 10.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
        if scenes:
            return scenes[0]["id"]
        time.sleep(0.05)
    raise TimeoutError("analysis never created scenes")


def test_preview_analysis_returns_scene_plans(client: TestClient) -> None:
    _, episode_id = create_episode_with_source(client)
    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze/preview")
    assert resp.status_code == 200
    body = resp.json()
    # P2-E1-T01: preview returns an envelope with the persisted snapshot id.
    assert body["snapshot_id"]
    assert body["episode_id"] == episode_id
    assert body["source_hash"]
    plans = body["plans"]
    assert len(plans) >= 2
    first = plans[0]
    assert first["scene_number"] == 1
    assert first["title"]
    assert first["location"]
    assert first["description"]


def test_analyze_creates_scenes_via_operation(client: TestClient) -> None:
    _, episode_id = create_episode_with_source(client)

    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    assert resp.status_code == 202
    op = resp.json()
    assert op["status"] == "queued" or op["status"] == "running"

    done = _wait_operation(client, op["operation_id"])
    assert done["status"] == "completed", done.get("error")
    result = done["result"]
    assert len(result["created_scene_ids"]) >= 2

    scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
    assert len(scenes) == len(result["created_scene_ids"])
    assert scenes[0]["scene_number"] == 1


def test_analyze_persists_mapped_fields(client: TestClient) -> None:
    """P1-E1-T01: ScenePlan title/location/time are persisted, not silently dropped."""
    _, episode_id = create_episode_with_source(client)
    done = _analyze(client, episode_id)
    assert done["status"] == "completed", done.get("error")
    plans = done["result"]["scene_plans"]

    scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
    assert len(scenes) == len(plans)
    for plan, scene in zip(plans, scenes, strict=True):
        assert scene["name"] == plan["title"]
        assert scene["location_id"] == plan["location"]
        assert scene["time_of_day"] == plan["time"]
        assert scene["description"] == plan["description"]
        assert scene["mood"] == plan["mood"]


def test_analyze_without_source_fails_cleanly(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "P"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "空"}).json()
    resp = client.post(f"/api/v1/episodes/{episode['id']}/analyze/preview")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_shots_creates_storyboard(client: TestClient) -> None:
    _, episode_id = create_episode_with_source(client)
    client.post(f"/api/v1/episodes/{episode_id}/analyze")
    scene_id = _first_scene(client, episode_id)

    done = _generate_shots(client, scene_id)
    assert done["status"] == "completed", done.get("error")
    assert len(done["result"]["created_shot_ids"]) >= 3

    storyboard = client.get(f"/api/v1/scenes/{scene_id}/storyboard").json()
    assert len(storyboard["shots"]) == len(done["result"]["created_shot_ids"])
    assert storyboard["shots"][0]["shot_number"] == 1
    assert storyboard["shots"][0]["shot_type"] in (
        "wide", "medium", "close_up", "extreme_close_up", "full",
    )


def test_duplicate_analysis_locked_and_idempotent(client: TestClient) -> None:
    """Two concurrent analyze calls on the same episode: both accepted, one lock
    serializes; the second is an idempotent no-op — no duplicate Scenes."""
    _, episode_id = create_episode_with_source(client)
    r1 = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    r2 = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    assert r1.status_code == 202 and r2.status_code == 202
    op1 = _wait_operation(client, r1.json()["operation_id"])
    op2 = _wait_operation(client, r2.json()["operation_id"])
    assert op1["status"] == "completed"
    assert op2["status"] == "completed"
    # P1-E1-T01: the second submission reuses the persisted scenes (no appending)
    assert op2["result"]["created_scene_ids"] == op1["result"]["created_scene_ids"]
    scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
    assert len(scenes) == len(op1["result"]["created_scene_ids"])


def test_analyze_replaces_ai_scenes_keeps_manual(client: TestClient) -> None:
    """P1-E1-T01: new source → AI scenes replaced (soft delete); manual scenes preserved."""
    _, episode_id = create_episode_with_source(client)
    done = _analyze(client, episode_id)
    first_ids = done["result"]["created_scene_ids"]

    manual = client.post(
        f"/api/v1/episodes/{episode_id}/scenes", json={"name": "手动补充场景"}
    ).json()
    assert manual["name"] == "手动补充场景"

    # changing the source produces a different analysis key → replace policy
    _ep_rev = client.get(f"/api/v1/episodes/{episode_id}").json()["revision"]
    resp = client.patch(
        f"/api/v1/episodes/{episode_id}",
        json={"revision": _ep_rev, "patch": {"source_text": NOVEL_TEXT + "\n追加的新章节：暗流涌动，旧敌归来。\n"}},
    )
    assert resp.status_code == 200

    done2 = _analyze(client, episode_id)
    assert done2["status"] == "completed", done2.get("error")
    second_ids = done2["result"]["created_scene_ids"]
    assert second_ids, "replace must create new scenes"
    assert not set(first_ids) & set(second_ids), "old AI scenes must be replaced"

    scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
    ids = [s["id"] for s in scenes]
    assert manual["id"] in ids, "manual scene must be preserved"
    assert set(second_ids) <= set(ids)
    assert not set(first_ids) & set(ids), "old AI scenes must be gone"


def test_generate_shots_idempotent_no_duplicates(client: TestClient) -> None:
    """P1-E1-T01: repeating the same shot-plan request does not append duplicate Shots."""
    _, episode_id = create_episode_with_source(client)
    client.post(f"/api/v1/episodes/{episode_id}/analyze")
    scene_id = _first_scene(client, episode_id)

    done1 = _generate_shots(client, scene_id)
    first_ids = done1["result"]["created_shot_ids"]
    assert len(first_ids) >= 3

    done2 = _generate_shots(client, scene_id)
    assert done2["status"] == "completed"
    assert done2["result"]["created_shot_ids"] == first_ids

    storyboard = client.get(f"/api/v1/scenes/{scene_id}/storyboard").json()
    assert [s["id"] for s in storyboard["shots"]] == first_ids


def test_generate_shots_replaces_ai_shots_keeps_manual(client: TestClient) -> None:
    """P1-E1-T01: changed scene context → AI shots replaced; manual shots preserved."""
    _, episode_id = create_episode_with_source(client)
    client.post(f"/api/v1/episodes/{episode_id}/analyze")
    scene_id = _first_scene(client, episode_id)

    done1 = _generate_shots(client, scene_id)
    first_ids = done1["result"]["created_shot_ids"]

    manual = client.post(f"/api/v1/scenes/{scene_id}/shots", json={"shot_type": "wide"}).json()

    # changing the scene context produces a different storyboard key → replace policy
    _rev = client.get(f"/api/v1/scenes/{scene_id}").json()["revision"]
    resp = client.patch(
        f"/api/v1/scenes/{scene_id}",
        json={"revision": _rev, "patch": {"name": "改名后的场景"}},
    )
    assert resp.status_code == 200

    done2 = _generate_shots(client, scene_id)
    assert done2["status"] == "completed", done2.get("error")
    second_ids = done2["result"]["created_shot_ids"]
    assert not set(first_ids) & set(second_ids), "old AI shots must be replaced"

    shots = client.get(f"/api/v1/scenes/{scene_id}/shots").json()
    ids = [s["id"] for s in shots]
    assert manual["id"] in ids, "manual shot must be preserved"
    assert set(second_ids) <= set(ids)
    assert not set(first_ids) & set(ids), "old AI shots must be gone"


def test_analyze_failure_leaves_no_partial_scenes(client: TestClient, monkeypatch) -> None:
    """P1-E1-T01: mid-batch failure → operation failed and ZERO scenes persisted."""
    from app.services.scene_service import SceneService as SceneSvc

    original = SceneSvc.create_scenes

    def flaky(self, episode_id, datas, analysis_key=None):
        original(self, episode_id, datas[:1], analysis_key=analysis_key)  # add 1 row, no commit
        raise RuntimeError("injected mid-batch failure")

    monkeypatch.setattr(SceneSvc, "create_scenes", flaky)
    _, episode_id = create_episode_with_source(client)

    done = _analyze(client, episode_id)
    assert done["status"] == "failed"
    assert client.get(f"/api/v1/episodes/{episode_id}/scenes").json() == []

    # recovery: a re-run without the fault succeeds (no poisoned state left)
    monkeypatch.undo()
    done2 = _analyze(client, episode_id)
    assert done2["status"] == "completed", done2.get("error")
    assert len(done2["result"]["created_scene_ids"]) >= 2


def test_generate_shots_failure_leaves_no_partial_shots(client: TestClient, monkeypatch) -> None:
    """P1-E1-T01: mid-batch failure → operation failed and ZERO shots persisted."""
    from app.services.shot_service import ShotService as ShotSvc

    original = ShotSvc.create_shots

    def flaky(self, scene_id, datas, analysis_key=None):
        original(self, scene_id, datas[:1], analysis_key=analysis_key)
        raise RuntimeError("injected mid-batch failure")

    monkeypatch.setattr(ShotSvc, "create_shots", flaky)
    _, episode_id = create_episode_with_source(client)
    client.post(f"/api/v1/episodes/{episode_id}/analyze")
    scene_id = _first_scene(client, episode_id)

    done = _generate_shots(client, scene_id)
    assert done["status"] == "failed"
    assert client.get(f"/api/v1/scenes/{scene_id}/shots").json() == []
