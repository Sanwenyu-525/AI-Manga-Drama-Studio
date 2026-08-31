"""Sprint 04 Step 1b: confirm (analyze) then diff persisted scenes vs preview snapshot (K1)."""
import json
import pathlib
import time
import httpx

API = "http://127.0.0.1:17820/api/v1"
state = json.loads(pathlib.Path("_validate/state.json").read_text(encoding="utf-8"))
eid = state["episode_id"]
preview = json.loads(pathlib.Path("_validate/preview1.json").read_text(encoding="utf-8"))

client = httpx.Client(timeout=30)

op = client.post(f"{API}/episodes/{eid}/analyze")
op.raise_for_status()
op_id = op.json().get("operation_id")
print("operation:", op_id)

status = None
start = time.time()
while time.time() - start < 180:
    r = client.get(f"{API}/operations/{op_id}")
    r.raise_for_status()
    body = r.json()
    status = body.get("status")
    print("  op status:", status)
    if status in ("completed", "failed", "cancelled"):
        if status == "failed":
            print("operation failed:", json.dumps(body, ensure_ascii=False)[:800])
        break
    time.sleep(5)

scenes = client.get(f"{API}/episodes/{eid}/scenes")
scenes.raise_for_status()
scenes_list = scenes.json()
print("\npersisted scene count:", len(scenes_list))

# --- K1 diff: preview plans vs persisted scenes ---
def norm(s):
    t = s.get("title") or s.get("scene_title") or ""
    c = s.get("content") or s.get("summary") or ""
    return (t.strip(), c.strip()[:60])

pv = [norm(p) for p in preview]
db = [norm(s) for s in scenes_list]
print("\n== K1 diff (preview vs persisted) ==")
print(f"counts: preview={len(pv)} persisted={len(db)}")
for i in range(max(len(pv), len(db))):
    a = pv[i] if i < len(pv) else None
    b = db[i] if i < len(db) else None
    flag = "SAME" if a and b and a[0] == b[0] else "DIFF"
    print(f"  [{i+1}] {flag} | pv={a[0]!r} | db={b[0]!r}")

# dump persisted scenes for the report
pathlib.Path("_validate/scenes1.json").write_text(
    json.dumps(scenes_list, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("\nscenes saved -> _validate/scenes1.json")