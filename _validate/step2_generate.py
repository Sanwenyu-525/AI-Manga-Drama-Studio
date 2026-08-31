"""Sprint 04 Step 2: dual-engine image run — 20 shots x (agnes + comfyui/zimage)."""
import json
import pathlib
import time
import httpx

API = "http://127.0.0.1:17820/api/v1"
state = json.loads(pathlib.Path("_validate/state.json").read_text(encoding="utf-8"))
shots_by_scene = json.loads(pathlib.Path("_validate/shots1.json").read_text(encoding="utf-8"))
scenes = json.loads(pathlib.Path("_validate/scenes1.json").read_text(encoding="utf-8"))

client = httpx.Client(timeout=60)

# --- pick 20 shots: scene1 all (14) + scene2 first 6 ---
selected = []
for sc in scenes:
    count = 14 if sc["scene_number"] == 1 else (6 if sc["scene_number"] == 2 else 0)
    for sh in shots_by_scene[sc["id"]][:count]:
        selected.append({"scene": sc["scene_number"], "shot_id": sh["id"], "shot_number": sh["shot_number"], "shot_type": sh["shot_type"]})
print("selected shots:", len(selected))

# --- collect full shot prompts ---
for s in selected:
    full = client.get(f"{API}/shots/{s['shot_id']}").json()
    s["image_prompt"] = full.get("image_prompt") or ""
    s["negative_prompt"] = full.get("negative_prompt") or ""

# --- create generations (both engines) ---
gens = []
for i, s in enumerate(selected):
    seed = 1000 + i * 2
    for engine, payload in [
        ("agnes", {"provider": "agnes"}),
        ("comfyui", {"provider": "comfyui", "workflow_id": "zimage_turbo"}),
    ]:
        body = {
            **payload,
            "prompt": s["image_prompt"],
            "negative_prompt": s["negative_prompt"],
            "seed": seed,
            "width": 512,
            "height": 912,
        }
        r = client.post(f"{API}/shots/{s['shot_id']}/generations", json=body)
        r.raise_for_status()
        g = r.json()
        gens.append({
            "gen_id": g["id"], "engine": engine, "seed": seed,
            "scene": s["scene"], "shot": s["shot_number"], "shot_type": s["shot_type"],
            "shot_id": s["shot_id"], "status": g["status"],
        })
        print(f"queued [{engine}] S{s['scene']}#{s['shot_number']} gen={g['id'][:8]} seed={seed}")

pathlib.Path("_validate/gens2.json").write_text(json.dumps(gens, ensure_ascii=False, indent=2), encoding="utf-8")
print("total queued:", len(gens))

# --- poll all to terminal ---
def poll(g):
    try:
        r = client.get(f"{API}/generations/{g['gen_id']}", timeout=20)
    except Exception as exc:
        return {"error": str(exc)}
    return r.json()

deadline = time.time() + 30 * 60
pending = list(gens)
out_dir = pathlib.Path("_validate/out")
while pending and time.time() < deadline:
    still = []
    for g in pending:
        b = poll(g)
        st = b.get("status")
        if st in ("completed", "failed", "cancelled"):
            g["status"] = st
            g["asset_id"] = b.get("output_asset_id")
            g["error"] = (b.get("error_message") or "")[:200]
            if st == "completed" and b.get("output_asset_id"):
                try:
                    c = client.get(f"{API}/assets/{b['output_asset_id']}/content", timeout=60)
                    d = out_dir / g["engine"]
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f"S{g['scene']}_{g['shot']:02d}_{g['engine']}.png").write_bytes(c.content)
                    g["downloaded"] = True
                except Exception as exc:
                    g["downloaded"] = False
                    g["error"] = (g.get("error") or "") + f" dl:{exc}"
            print(f"done [{g['engine']}] S{g['scene']}#{g['shot']} -> {st}" + (f" dl" if g.get("downloaded") else ""))
        else:
            still.append(g)
    pending = still
    if pending:
        time.sleep(4)

print("\n== summary ==")
ok = sum(1 for g in gens if g.get("status") == "completed" and g.get("downloaded"))
print(f"completed+downloaded: {ok}/{len(gens)}")
for g in gens:
    if g.get("status") != "completed":
        print(f"  NOT-OK {g['engine']} S{g['scene']}#{g['shot']}: {g.get('status')} {g.get('error')}")
pathlib.Path("_validate/gens2.json").write_text(json.dumps(gens, ensure_ascii=False, indent=2), encoding="utf-8")