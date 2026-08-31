"""Sprint 04 Step 1a: run analyze/preview against the real LLM, snapshot the plans."""
import json
import pathlib
import httpx

API = "http://127.0.0.1:17820/api/v1"
state = json.loads(pathlib.Path("_validate/state.json").read_text(encoding="utf-8"))
eid = state["episode_id"]

client = httpx.Client(timeout=180)
resp = client.post(f"{API}/episodes/{eid}/analyze/preview")
resp.raise_for_status()
plans = resp.json()

pathlib.Path("_validate/preview1.json").write_text(
    json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("preview scene count:", len(plans))
for i, s in enumerate(plans, 1):
    print(f"  [{i}] {s.get('title', s.get('scene_title', '(no title)'))!r}  type={s.get('scene_type','')}")