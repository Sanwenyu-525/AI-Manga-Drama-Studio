"""Sprint 04 Step 1b-2: correct K1 diff using scene.name / description."""
import json
import pathlib

preview = json.loads(pathlib.Path("_validate/preview1.json").read_text(encoding="utf-8"))
scenes = json.loads(pathlib.Path("_validate/scenes1.json").read_text(encoding="utf-8"))

print(f"counts: preview={len(preview)} persisted={len(scenes)}")
same = 0
for i, (p, s) in enumerate(zip(preview, scenes), 1):
    pt = (p.get("title") or p.get("scene_title") or "").strip()
    st = (s.get("name") or "").strip()
    pd = (p.get("description") or p.get("content") or "").strip()[:80]
    sd = (s.get("description") or "").strip()[:80]
    t_same = pt == st
    d_same = pd == sd
    same += int(t_same and d_same)
    print(f"  [{i}] title_same={t_same} desc_same={d_same}")
    print(f"      pv: {pt!r}")
    print(f"      db: {st!r}")
    print(f"      pv-desc: {pd!r}")
    print(f"      db-desc: {sd!r}")
print(f"K1 same-pair count: {same}/{len(scenes)}")