"""WorkflowMapper (backend-architecture §21, §42; mvp-spec §66-67).

Loads a ComfyUI workflow template (API format) and injects Studio params via
$PLACEHOLDER tokens. Studio never needs to understand KSampler/CLIP/VAE —
it only knows prompt / negative_prompt / seed / width / height (contract §42).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.core.errors import ComfyUIError
from app.core.logging import get_logger

logger = get_logger("comfyui.mapper")

DEFAULT_WORKFLOW = Path(__file__).resolve().parents[3] / "workflows" / "default_image_api.json"

PLACEHOLDERS = ("$PROMPT", "$NEGATIVE_PROMPT", "$SEED", "$WIDTH", "$HEIGHT", "$REFERENCE_IMAGE")


class WorkflowMapper:
    def __init__(self, workflow_path: Path | None = None) -> None:
        self.workflow_path = workflow_path or DEFAULT_WORKFLOW

    def load_template(self) -> dict:
        if not self.workflow_path.exists():
            raise ComfyUIError(f"Workflow template not found: {self.workflow_path}")
        return json.loads(self.workflow_path.read_text(encoding="utf-8"))

    def build(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_images: list[str] | None = None,
    ) -> dict:
        """Return a workflow with placeholders substituted (reference upload is caller's job)."""
        template = self.load_template()
        resolved_seed = seed if seed is not None else random.randint(0, 2**31)
        refs = reference_images or []
        ref_value = refs[0] if refs else ""

        values = {
            "$PROMPT": prompt,
            "$NEGATIVE_PROMPT": negative_prompt or "",
            "$SEED": resolved_seed,
            "$WIDTH": width or 512,
            "$HEIGHT": height or 912,
            "$REFERENCE_IMAGE": ref_value,
        }

        workflow = json.loads(json.dumps(template))  # deep copy
        for node in workflow.values():
            inputs = node.get("inputs", {})
            for key, value in list(inputs.items()):
                if isinstance(value, str) and value in values:
                    inputs[key] = values[value]
        return workflow
