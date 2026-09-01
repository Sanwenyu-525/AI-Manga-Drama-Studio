"""P2-E3-T02/T03 live smoke: R1 auto-apply + ChangeSet + Undo + R2 approval.

Run against a fake-LLM server (STUDIO_LLM_MODE=fake). Verifies:
1. R1 "改成近景" → auto-applied (rev+1) + change set recorded, no proposal
2. Undo → restored (rev+1 again), compensating change set linked
3. R2 "重新生成" → waiting_human proposal (risk metadata), no generation
4. approve → generation created
"""
import time

import httpx

BASE = "http://127.0.0.1:17899/api/v1"
c = httpx.Client(base_url=BASE, timeout=30)


def wait_status(run_id, statuses, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = c.get(f"/agent/runs/{run_id}").json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} stuck at {run['status']}")


def main():
    p = c.post("/projects", json={"name": "SmokeP2E3"}).json()
    e = c.post(f"/projects/{p['id']}/episodes", json={"title": "E1"}).json()
    s = c.post(f"/episodes/{e['id']}/scenes", json={"name": "S1"}).json()
    sh = c.post(f"/scenes/{s['id']}/shots", json={"shot_type": "medium", "image_prompt": "a girl in rain"}).json()

    # ---- 1. R1 auto-apply + ChangeSet ----
    run1 = c.post(
        "/agent/director/runs",
        json={"project_id": p["id"], "message": "把这个镜头改成近景。", "selection": {"shot_ids": [sh["id"]], "scene_id": s["id"]}},
    ).json()
    done = wait_status(run1["id"], {"completed", "failed", "cancelled"})
    after = c.get(f"/shots/{sh['id']}").json()
    assert done["status"] == "completed", done
    assert after["shot_type"] == "close_up" and after["revision"] == 2, after
    assert c.get(f"/agent/runs/{run1['id']}/proposals").json() == []
    cs = c.get("/agent/change-sets", params={"run_id": run1["id"]}).json()
    assert len(cs) == 1 and cs[0]["before"] == {"shot_type": "medium"} and cs[0]["after"] == {"shot_type": "close_up"}, cs
    print("1. R1 auto-apply + change set: OK (close_up, rev 2)")

    # ---- 2. Undo ----
    undone = c.post(f"/agent/change-sets/{cs[0]['id']}/undo", json={"force": False}).json()
    restored = c.get(f"/shots/{sh['id']}").json()
    assert restored["shot_type"] == "medium" and restored["revision"] == 3, restored
    assert undone["source"] == "undo" and undone["after"] == {"shot_type": "medium"}, undone
    again = c.post(f"/agent/change-sets/{cs[0]['id']}/undo", json={"force": False})
    assert again.status_code == 409, again.text
    print("2. Undo (compensating change, idempotent 409): OK (medium, rev 3)")

    # ---- 3. R2 requires approval ----
    run2 = c.post(
        "/agent/director/runs",
        json={"project_id": p["id"], "message": "重新生成这个镜头。", "selection": {"shot_ids": [sh["id"]], "scene_id": s["id"]}},
    ).json()
    waiting = wait_status(run2["id"], {"waiting_human", "waiting_approval", "completed", "failed"})
    assert waiting["status"] == "waiting_human", waiting
    proposal = waiting["pending_proposals"][0]
    assert proposal["tool"] == "generate_image" and proposal["risk_level"] == "R2", proposal
    assert proposal["estimated_tasks"] == 1 and proposal["expires_at"], proposal
    assert c.get(f"/shots/{sh['id']}/generations").json() == []
    print("3. R2 waiting_human + risk metadata + zero generations: OK")

    # ---- 4. approve creates the generation ----
    approved = c.post(f"/agent/proposals/{proposal['id']}/approve").json()
    assert approved["status"] == "applied", approved
    gens = c.get(f"/shots/{sh['id']}/generations").json()
    assert len(gens) == 1 and gens[0]["type"] == "image", gens
    print("4. approve creates generation: OK")

    print("\nALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
