"""Sprint 04 Step 1c: generate shot plans per scene (real LLM), collect image_prompts."""
import json
import pathlib
import time
import httpx

API = "http://127.0.0.1:17820/api/v1"
state = json.loads(pathlib.Path("_validate/state.json").read_text(encoding="utf-8"))
scenes = json.loads(pathlib.Path("_validate/scenes1.json").read_text(encoding="utf-8"))

client = httpx.Client(timeout=60)
all_shots = {}

for sc in scenes:
    sid = sc["id"]
    print(f"--- scene {sc['scene_number']} {sc['name']!r} ---")
    op = client.post(f"{API}/scenes/{sid}/generate-shots")
    op.raise_for_status()
    op_id = op.json().get("operation_id")
    print("  op:", op_id)
    start = time.time()
    while time.time() - start < 300:
        r = client.get(f"{API}/operations/{op_id}")
        status = r.json().get("status")
        if status in ("completed", "failed", "cancelled"):
            if status != "completed":
                print("  op failed:", json.dumps(r.json(), ensure_ascii=False)[:400])
            break
        time.sleep(5)
    sb = client.get(f"{API}/scenes/{sid}/storyboard")
    sb.raise_for_status()
    data = sb.json()
    shots = data.get("shots", data) if isinstance(data, dict) else data
    print("  shots:", len(shots))
    for sh in shots:
        print(f"    #{sh.get('shot_number')} type={sh.get('shot_type')} dur={sh.get('duration')} action={str(sh.get('action'))[:24]!r}")
    all_shots[sid] = shots

pathlib.Path("_validate/shots1.json").write_text(
    json.dumps(all_shots, ensure_ascii=False, indent=2), encoding="utf-8"
)
total = sum(len(v) for v in all_shots.values())
print("TOTAL shots:", total, "-> _validate/shots1.json")