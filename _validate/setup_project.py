"""Sprint 04 Step 0c/Step1: create validation project + episode with the sampled source."""
import json
import pathlib
import httpx

API = "http://127.0.0.1:17820/api/v1"
client = httpx.Client(timeout=20)

# 1) project
pr = client.post(f"{API}/projects", json={"name": "真实链路验证-街球", "description": "Sprint 04 real chain validation; source = demo EP1 slice"})
pr.raise_for_status()
project = pr.json()
pid = project["id"]
print("project:", pid, project.get("name"))

# 2) episode with source slice
text = pathlib.Path("_validate/chapter_sample.txt").read_text(encoding="utf-8")
ep = client.post(f"{API}/projects/{pid}/episodes", json={"title": "街球初战", "source_text": text})
ep.raise_for_status()
episode = ep.json()
eid = episode["id"]
print("episode:", eid, "source_len:", len(text))

pathlib.Path("_validate/state.json").write_text(
    json.dumps({"project_id": pid, "episode_id": eid}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print("state saved")