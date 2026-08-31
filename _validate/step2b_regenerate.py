"""Sprint 04 Step 2b: regenerate the NOT-OK shots on BOTH engines (single-variable prompt fix)."""
import json
import pathlib
import time
import httpx

API = "http://127.0.0.1:17820/api/v1"
client = httpx.Client(timeout=60)

RETRY_SHOTS = {  # shot -> reason (from quick review)
    "S1_05": "action semantic drift", "S1_06": "object hallucination",
    "S1_07": "object hallucination (billiard ball)", "S1_08": "wrong scale + age",
    "S1_10": "subject mismatch (two men conspiring)", "S1_12": "floating bottle",
    "S1_14": "environment hallucination (temple)",
}
AGE_FIX = ", the main subject is an 8-year-old Chinese boy"

gens = json.loads(pathlib.Path("_validate/gens2.json").read_text(encoding="utf-8"))
# map S{scene}#{shot} -> ids of the two engines' generations; fetch prompts from the shots DB
shot_cache = {}
queue = []
for key, reason in RETRY_SHOTS.items():
    parts = key.split("_")  # S1_05 -> scene=1 shot=5
    scene, shot = int(parts[0][1:]), int(parts[1])
    # find original generation ids for this shot+engine
    for g in gens:
        if g["scene"] == scene and g["shot"] == shot:
            gen_id = g["gen_id"]
            # fetch shot full to get canonical prompt
            if shot_cache.get((scene, shot)) is None:
                r = client.get(f"{API}/shots/{g['shot_id']}")
                f = r.json()
                shot_cache[(scene, shot)] = {
                    "id": g["shot_id"], "prompt": f.get("image_prompt") or "",
                    "negative": f.get("negative_prompt") or "",
                }
            queue.append({"engine": g["engine"], "key": key, "reason": reason})

new_seed = 9000
for i, q in enumerate(queue):
    sc = int(q["key"].split("_")[0][1:]); sh = int(q["key"].split("_")[1])
    meta = shot_cache[(sc, sh)]
    prompt = meta["prompt"] + AGE_FIX
    body = {
        "provider": q["engine"], "prompt": prompt, "negative_prompt": meta["negative"],
        "seed": new_seed + i, "width": 512, "height": 912,
    }
    if q["engine"] == "comfyui":
        body["workflow_id"] = "zimage_turbo"
    r = client.post(f"{API}/shots/{meta['id']}/generations", json=body)
    r.raise_for_status()
    g = r.json()
    q["gen_id"] = g["id"]
    print(f"queued [{q['engine']}] {q['key']} seed={body['seed']}")

# poll
out = pathlib.Path("_validate/out/regenerated")
out.mkdir(parents=True, exist_ok=True)
deadline = time.time() + 25 * 60
pending = list(queue)
while pending and time.time() < deadline:
    still = []
    for q in pending:
        b = client.get(f"{API}/generations/{q['gen_id']}").json()
        st = b.get("status")
        if st in ("completed", "failed", "cancelled"):
            q["status"] = st
            q["error"] = (b.get("error_message") or "")[:200]
            if st == "completed" and b.get("output_asset_id"):
                c = client.get(f"{API}/assets/{b['output_asset_id']}/content", timeout=60)
                (out / f"{q['key']}_{q['engine']}_r.png").write_bytes(c.content)
                q["downloaded"] = True
            print(f"done [{q['engine']}] {q['key']} -> {st}" + (" dl" if q.get("downloaded") else ""))
        else:
            still.append(q)
    pending = still
    if pending:
        time.sleep(4)

pathlib.Path("_validate/regen2.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
print("regen completed:", sum(1 for q in queue if q.get("downloaded")), "/", len(queue))