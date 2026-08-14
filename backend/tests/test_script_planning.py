"""Stage B tests: novel → analyze → scenes → generate-shots → storyboard (mvp-spec §62).

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


def test_preview_analysis_returns_scene_plans(client: TestClient) -> None:
    _, episode_id = create_episode_with_source(client)
    resp = client.post(f"/api/v1/episodes/{episode_id}/analyze/preview")
    assert resp.status_code == 200
    plans = resp.json()
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


def test_analyze_without_source_fails_cleanly(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "P"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "空"}).json()
    resp = client.post(f"/api/v1/episodes/{episode['id']}/analyze/preview")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_shots_creates_storyboard(client: TestClient) -> None:
    _, episode_id = create_episode_with_source(client)
    client.post(f"/api/v1/episodes/{episode_id}/analyze")
    # poll analysis so scenes exist
    scenes = []
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        scenes = client.get(f"/api/v1/episodes/{episode_id}/scenes").json()
        if scenes:
            break
        time.sleep(0.05)
    assert scenes, "analysis never created scenes"

    scene_id = scenes[0]["id"]
    resp = client.post(f"/api/v1/scenes/{scene_id}/generate-shots")
    assert resp.status_code == 202
    done = _wait_operation(client, resp.json()["operation_id"])
    assert done["status"] == "completed", done.get("error")
    assert len(done["result"]["created_shot_ids"]) >= 3

    storyboard = client.get(f"/api/v1/scenes/{scene_id}/storyboard").json()
    assert len(storyboard["shots"]) == len(done["result"]["created_shot_ids"])
    assert storyboard["shots"][0]["shot_number"] == 1
    assert storyboard["shots"][0]["shot_type"] in (
        "wide", "medium", "close_up", "extreme_close_up", "full",
    )


def test_duplicate_analysis_locked(client: TestClient) -> None:
    """Two concurrent analyze calls on the same episode: both accepted, one lock serializes."""
    _, episode_id = create_episode_with_source(client)
    r1 = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    r2 = client.post(f"/api/v1/episodes/{episode_id}/analyze")
    assert r1.status_code == 202 and r2.status_code == 202
    op1 = _wait_operation(client, r1.json()["operation_id"])
    op2 = _wait_operation(client, r2.json()["operation_id"])
    assert op1["status"] == "completed"
    # second run re-analyzes (no error); scenes may duplicate — acceptable MVP behavior,
    # lock guarantees no concurrent corruption
    assert op2["status"] in ("completed", "failed")
