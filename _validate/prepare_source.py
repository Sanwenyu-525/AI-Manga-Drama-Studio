"""Sprint 04 Step 0c: slice a ~2400-char narrative segment from the demo EP1 source."""
import pathlib
import httpx

API = "http://127.0.0.1:17820/api/v1"
r = httpx.get(f"{API}/episodes/647cc87d-8233-4e84-9568-1fea8eb0efdd", timeout=10)
r.raise_for_status()
src = r.json()["source_text"]
seg = src[400:400 + 2400]  # skip the leading chapter title block, take a continuous slice
out = pathlib.Path("_validate") / "chapter_sample.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(seg, encoding="utf-8")
print("sample length:", len(seg))
print("sample head:", seg[:120].replace("\n", " "))