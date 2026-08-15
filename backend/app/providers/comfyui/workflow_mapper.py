"""WorkflowMapper (backend-architecture §21, §42; mvp-spec §66-67).

Loads a ComfyUI workflow template (API format) and injects Studio params via
$PLACEHOLDER tokens. Studio never needs to understand KSampler/CLIP/VAE —
it only knows prompt / negative_prompt / seed / width / height (contract §42).

P1-E2-T01 (修复真实 ComfyUI workflow 与 Provider 选择):

- workflow_id 决定模板：受校验的 catalog（"default_image_api" → default_image_api.json），
  未知 id 在 Generation 创建时返回 422，绝不静默回落。
- 模板定位：settings.workflows_dir（默认仓库根 workflows/，可用 STUDIO_WORKFLOWS_DIR
  覆盖以适配打包布局）；不再使用错误的 parents[3] 相对路径。
- preflight：模板必须（a）是合法 JSON，（b）声明恰好一个 SaveImage 输出节点，
  （c）包含全部必需 placeholder；缺失时 ComfyUIError，生成前失败。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.core.config import settings
from app.core.errors import ComfyUIError, ValidationError
from app.core.logging import get_logger

logger = get_logger("comfyui.mapper")

# Canonical workflow catalog: workflow_id → template filename under settings.workflows_dir.
WORKFLOW_CATALOG: dict[str, str] = {
    "default_image_api": "default_image_api.json",
}
DEFAULT_WORKFLOW_ID = "default_image_api"

# Placeholders required for a working image workflow (preflight contract).
REQUIRED_PLACEHOLDERS = ("$PROMPT", "$SEED", "$WIDTH", "$HEIGHT")
OUTPUT_NODE_CLASS = "SaveImage"

PLACEHOLDERS = ("$PROMPT", "$NEGATIVE_PROMPT", "$SEED", "$WIDTH", "$HEIGHT", "$REFERENCE_IMAGE")


def resolve_workflow_path(workflow_id: str | None, workflows_dir: Path | None = None) -> Path:
    """Map a canonical workflow_id to a template path.

    Raises ValidationError (422) for unknown ids — the caller decides whether to
    surface it at creation time; the mapper never silently falls back.
    """
    wid = workflow_id or DEFAULT_WORKFLOW_ID
    filename = WORKFLOW_CATALOG.get(wid)
    if filename is None:
        raise ValidationError(
            "Unknown workflow template.",
            {"workflow_id": wid, "supported": sorted(WORKFLOW_CATALOG)},
        )
    base = workflows_dir or settings.workflows_dir
    return base / filename


class WorkflowMapper:
    """Template loader + placeholder injector for ONE workflow id."""

    def __init__(self, workflow_id: str | None = None, workflows_dir: Path | None = None) -> None:
        self.workflow_id = workflow_id or DEFAULT_WORKFLOW_ID
        self.workflow_path = resolve_workflow_path(self.workflow_id, workflows_dir)
        self._output_node_id: str | None = None

    def load_template(self) -> dict:
        if not self.workflow_path.exists():
            raise ComfyUIError(
                f"Workflow template not found: {self.workflow_path}",
                {"workflow_id": self.workflow_id, "path": str(self.workflow_path)},
            )
        try:
            template = json.loads(self.workflow_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ComfyUIError(
                f"Workflow template is not valid JSON: {self.workflow_path.name}",
                {"workflow_id": self.workflow_id},
            ) from exc
        self._preflight(template)
        return template

    def preflight(self) -> None:
        """Validate the template WITHOUT building (used by provider test connection)."""
        self.load_template()

    @property
    def output_node_id(self) -> str | None:
        return self._output_node_id

    def _preflight(self, template: dict) -> None:
        """P1-E2-T01: fail fast on missing output node / required placeholders."""
        outputs = [
            node_id
            for node_id, node in template.items()
            if isinstance(node, dict) and node.get("class_type") == OUTPUT_NODE_CLASS
        ]
        if len(outputs) != 1:
            raise ComfyUIError(
                f"Workflow template must declare exactly one {OUTPUT_NODE_CLASS} output node.",
                {"workflow_id": self.workflow_id, "output_nodes": len(outputs)},
            )
        self._output_node_id = outputs[0]

        input_values = [
            value
            for node in template.values()
            if isinstance(node, dict)
            for value in node.get("inputs", {}).values()
        ]
        missing = [
            placeholder
            for placeholder in REQUIRED_PLACEHOLDERS
            if placeholder not in input_values
        ]
        if missing:
            raise ComfyUIError(
                f"Workflow template is missing required placeholders: {', '.join(missing)}.",
                {"workflow_id": self.workflow_id, "missing": missing},
            )

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
