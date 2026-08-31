"""Sprint 04 Step 0b: preflight + injection check for the Z-Image workflow template."""
import json

from app.providers.comfyui.workflow_mapper import WorkflowMapper

m = WorkflowMapper("zimage_turbo")
m.preflight()
print("preflight OK, output node:", m.output_node_id)
wf = m.build(prompt="hello", negative_prompt="", seed=42, width=512, height=912)
s = json.dumps(wf)
for t in ("$PROMPT", "$SEED", "$WIDTH", "$HEIGHT", "$NEGATIVE_PROMPT"):
    assert t not in s, f"leftover placeholder {t}"
n = json.loads(s)
print(
    "build OK; steps=", n["7"]["inputs"]["steps"],
    "cfg=", n["7"]["inputs"]["cfg"],
    "size=", n["5"]["inputs"]["width"], "x", n["5"]["inputs"]["height"],
)