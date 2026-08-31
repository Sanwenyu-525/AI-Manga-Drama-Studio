"""Sprint 06 live E2E: P2-E1-T01 snapshot preview → confirm（真实运行后端）。"""
import json
import pathlib
import time
import httpx

API = "http://127.0.0.1:17820/api/v1"
client = httpx.Client(timeout=120)

# 1) 新建验证项目/剧集（源文沿用验证样本）
text = pathlib.Path("_validate/chapter_sample.txt").read_text(encoding="utf-8")
pr = client.post(f"{API}/projects", json={"name": "P2E1T01-实证"}).raise_for_status()
pid = client.post(f"{API}/projects/{pr.json()['id']}/episodes", json={"title": "快照实证", "source_text": text}).raise_for_status()
eid = pid.json()["id"]
print("episode:", eid)

# 2) preview → 信封 + snapshot_id（真实 LLM）
t0 = time.time()
pv = client.post(f"{API}/episodes/{eid}/analyze/preview").raise_for_status()
preview = pv.json()
print(f"preview: snapshot={preview['snapshot_id'][:8]} plans={len(preview['plans'])} model={preview['model']} ({time.time()-t0:.1f}s)")

# 3) confirm 只提交快照（零 LLM，应显著快于 preview）
t0 = time.time()
op = client.post(f"{API}/episodes/{eid}/analyze", json={"snapshot_id": preview["snapshot_id"]}).raise_for_status().json()
while True:
    body = client.get(f"{API}/operations/{op['operation_id']}").raise_for_status().json()
    if body["status"] in ("completed", "failed"):
        break
    time.sleep(1)
confirm_secs = time.time() - t0
print(f"confirm: {body['status']} in {confirm_secs:.1f}s, scenes={len(body['result']['created_scene_ids'])}")
assert body["status"] == "completed", body.get("error")
assert confirm_secs < 10, "confirm 不应再有 LLM 耗时"

# 4) 写入内容与预览逐项一致
scenes = client.get(f"{API}/episodes/{eid}/scenes").raise_for_status().json()
for plan, scene in zip(preview["plans"], scenes, strict=True):
    assert scene["name"] == plan["title"] and scene["description"] == plan["description"]
print("field-by-field match: OK")

# 5) 幂等重放
op2 = client.post(f"{API}/episodes/{eid}/analyze", json={"snapshot_id": preview["snapshot_id"]}).raise_for_status().json()
while True:
    b2 = client.get(f"{API}/operations/{op2['operation_id']}").raise_for_status().json()
    if b2["status"] in ("completed", "failed"):
        break
    time.sleep(1)
assert b2["result"]["created_scene_ids"] == body["result"]["created_scene_ids"]
scenes2 = client.get(f"{API}/episodes/{eid}/scenes").raise_for_status().json()
assert len(scenes2) == len(scenes)
print("idempotent replay: OK")

# 6) latest snapshot 状态追溯
latest = client.get(f"{API}/episodes/{eid}/analysis-snapshots/latest").raise_for_status().json()
assert latest["status"] == "confirmed" and latest["created_scene_ids"]
print(f"latest snapshot: {latest['status']} provenance={latest['model']}/{latest['prompt_version']}/{latest['schema_version']}")

# 7) 过期语义：新 preview（pending）→ 改原文 → confirm 应失败
#    （已 confirmed 的快照走幂等重放，不重复测过期——那是另一条已验证的路径）
pv2 = client.post(f"{API}/episodes/{eid}/analyze/preview").raise_for_status().json()
ep = client.get(f"{API}/episodes/{eid}").raise_for_status().json()
client.patch(f"{API}/episodes/{eid}", json={"revision": ep["revision"], "patch": {"source_text": text + "\n新段落"}}).raise_for_status()
op3 = client.post(f"{API}/episodes/{eid}/analyze", json={"snapshot_id": pv2["snapshot_id"]}).raise_for_status().json()
while True:
    b3 = client.get(f"{API}/operations/{op3['operation_id']}").raise_for_status().json()
    if b3["status"] in ("completed", "failed"):
        break
    time.sleep(1)
assert b3["status"] == "failed" and "preview" in (b3.get("error") or "").lower()
latest = client.get(f"{API}/episodes/{eid}/analysis-snapshots/latest").raise_for_status().json()
assert latest["status"] == "expired"
print("expiry on source change: OK (snapshot=expired)")

print("\nLIVE E2E: ALL PASS")
pathlib.Path("_validate/p2e1t01_live.json").write_text(
    json.dumps({"episode_id": eid, "snapshot_id": preview["snapshot_id"], "confirm_secs": round(confirm_secs, 2)}, indent=2),
    encoding="utf-8",
)