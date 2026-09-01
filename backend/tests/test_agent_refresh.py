"""自主迭代 05 — AI Director 刷新恢复测试。

覆盖：run 明细返回确定性消息转录（messages）/ 项目最近会话列表端点（新在前）/
waiting_human 转录含审批提示 / _transcript 的 failed + clarification 边界。
"""

import time

from fastapi.testclient import TestClient

from app.agents.director import runner


def _wait_status(client: TestClient, run_id: str, statuses: set[str], timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/agent/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"agent run {run_id} did not reach {statuses}")


def _make_project_shot(client: TestClient) -> dict:
    project = client.post("/api/v1/projects", json={"name": "Refresh"}).json()
    episode = client.post(f"/api/v1/projects/{project['id']}/episodes", json={"title": "E1"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", json={"name": "S1"}).json()
    shots = [
        client.post(
            f"/api/v1/scenes/{scene['id']}/shots",
            json={"shot_type": "medium", "image_prompt": f"prompt {i}"},
        ).json()
        for i in range(2)
    ]
    return {"project_id": project["id"], "scene_id": scene["id"], "shots": shots}


def _run_director(client: TestClient, ctx: dict, message: str, shot: dict) -> str:
    resp = client.post(
        "/api/v1/agent/director/runs",
        json={
            "project_id": ctx["project_id"],
            "message": message,
            "selection": {"shot_ids": [shot["id"]], "scene_id": ctx["scene_id"]},
        },
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def test_run_detail_includes_transcript_messages(client: TestClient) -> None:
    """完成的 run：messages = [user 指令, assistant 摘要]——刷新后可水合对话流。"""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][1]
    run_id = _run_director(client, ctx, "把这个镜头改成近景。", shot)
    done = _wait_status(client, run_id, {"completed", "failed"})
    assert done["status"] == "completed", done.get("result")

    messages = done["messages"]
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "把这个镜头改成近景。"
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"]


def test_list_runs_returns_latest_newest_first_with_messages(client: TestClient) -> None:
    """GET /agent/runs?project_id= 返回最近会话（新在前），每条带 messages。"""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    r1 = _run_director(client, ctx, "把这个镜头改成近景。", shot)
    _wait_status(client, r1, {"completed", "failed"})
    # 第二次：无 selection 的模糊指令 → clarification（仍是 completed，转录不同）
    r2 = _run_director(client, ctx, "把这个改一下", {"id": "nope"})
    _wait_status(client, r2, {"completed", "failed"})

    runs = client.get(
        "/api/v1/agent/runs", params={"project_id": ctx["project_id"], "limit": 5}
    ).json()
    assert len(runs) >= 2
    assert runs[0]["id"] == r2  # 最新在前（刷新恢复取 limit=1 即得上次会话）
    assert all("messages" in r for r in runs)
    assert runs[0]["messages"][0]["role"] == "user"


def test_waiting_human_transcript_includes_approval_prompt(client: TestClient) -> None:
    """generate_image（R2 提案）→ WAITING_HUMAN：转录含审批提示（刷新后仍可见待审批态）。"""
    ctx = _make_project_shot(client)
    shot = ctx["shots"][0]
    run_id = _run_director(client, ctx, "重新生成这个镜头。", shot)
    waiting = _wait_status(client, run_id, {"waiting_human", "waiting_approval"})
    assert any("需要审批" in m["content"] for m in waiting["messages"])
    assert any("重新生成这个镜头。" == m["content"] for m in waiting["messages"] if m["role"] == "user")


def test_transcript_failed_and_clarification_edges() -> None:
    """_transcript 边界：failed 追加错误消息；clarification 优先于 summary。"""
    from types import SimpleNamespace

    # failed：user + failed 错误
    failed = SimpleNamespace(
        input_json='{"message": "改这个"}',
        result_json='{"error": "boom"}',
        status="failed",
        error_message="graph crashed",
    )
    msgs = runner._transcript(failed)  # noqa: SLF001 — 白盒单测
    assert msgs[0] == {"role": "user", "content": "改这个"}
    assert msgs[-1]["role"] == "assistant"
    assert "graph crashed" in msgs[-1]["content"]

    # clarification 优先于 summary
    clar = SimpleNamespace(
        input_json='{"message": "改这个"}',
        result_json='{"summary": "完成。", "clarification": "你希望怎么改？"}',
        status="completed",
        error_message=None,
    )
    msgs = runner._transcript(clar)  # noqa: SLF001
    assert msgs[-1]["content"] == "你希望怎么改？"
