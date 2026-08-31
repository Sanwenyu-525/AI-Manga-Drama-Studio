"""WorkflowMapper (backend-architecture §21, §42; mvp-spec §66-67).

Loads a ComfyUI workflow template (API format) and injects Studio params via
$PLACEHOLDER tokens. Studio never needs to understand KSampler/CLIP/VAE —
it only knows prompt / negative_prompt / seed / width / height (contract §42).

P1-E2-T01 (fix real ComfyUI workflow + Provider selection):

- workflow_id decides the template: a validated catalog ("default_image_api" ->
  default_image_api.json); unknown id returns 422 at generation creation, never a
  silent fallback.
- Template location: settings.workflows_dir (default repo root workflows/, can be
  overridden with STUDIO_WORKFLOWS_DIR for packaged layouts); no more erroneous
  parents[3] relative path.
- preflight: template must (a) be valid JSON, (b) declare exactly one SaveImage
  output node, and (c) satisfy the WorkflowSchema template contract (P4-T005) —
  every token used is declared and every required placeholder is present. Failures
  surface as ComfyUIError / ValidationError before generation.

P4-T006 (formal Input Mapping):

- The placeholder-mapping table now lives in WorkflowSchema (workflow_schema.py):
  logical parameter name -> placeholder token ($PROMPT etc.). build() drives
  substitution through the schema's coerce step instead of hand-writing the values
  dict. The external build() signature is unchanged, so existing callers
  (ComfyUIProvider.generate, provider test preflight) are unaffected, and Studio
  still never exposes a node_id.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.core.errors import ComfyUIError, ValidationError
from app.core.logging import get_logger
from app.providers.comfyui.workflow_schema import (
    IMAGE_PARAMETERS,
    RESERVED_PARAMETERS,
)
from app.providers.comfyui.workflow_schema import REQUIRED_PLACEHOLDERS  # noqa: F401 — re-export for callers/tests
from app.providers.comfyui.workflow_schema import WorkflowSchema

logger = get_logger("comfyui.mapper")

# Canonical workflow catalog seed: workflow_id -> template filename under the
# workflows dir. Sprint 05 (P2-2): the runtime catalog is DISCOVERED from the
# workflows dir (see _resolve_catalog) — dropping a new template JSON into
# workflows/ makes it immediately resolvable without a code change. The seed
# only pins templates whose filename stem differs from the canonical id.
WORKFLOW_CATALOG: dict[str, str] = {
    "default_image_api": "default_image_api.json",
}
DEFAULT_WORKFLOW_ID = "default_image_api"


def _resolve_catalog(workflows_dir: Path | None = None) -> dict[str, str]:
    """Yield a workflow_id -> template filename mapping for the given dir.

    Auto-discovery: every *.json under the workflows dir is registered by its
    filename stem, then pinned overrides (WORKFLOW_CATALOG) win on collision.
    This is what makes Sprint 04's zimage_turbo_api.json resolvable with zero
    code changes (P2-2: catalog extension is flow-based, not edit-a-dict).
    """
    base = workflows_dir or settings.workflows_dir
    catalog = dict(WORKFLOW_CATALOG)
    if base is not None and base.is_dir():
        for path in sorted(base.glob("*.json")):
            catalog[path.stem] = path.name
    return catalog

# Placeholders required for a working image workflow (preflight contract) — derived
# from the declarative schema. REQUIRED_PLACEHOLDERS is re-exported from
# workflow_schema (kept for backward compatibility with callers/tests).
OUTPUT_NODE_CLASS = "SaveImage"

# All placeholder tokens recognised by the image schema (active + reserved).
PLACEHOLDERS: tuple[str, ...] = tuple(
    p.placeholder for p in (IMAGE_PARAMETERS + RESERVED_PARAMETERS)
)


def _default_schema() -> WorkflowSchema:
    return WorkflowSchema()


def resolve_workflow_path(workflow_id: str | None, workflows_dir: Path | None = None) -> Path:
    """Map a canonical workflow_id to a template path (auto-discovered catalog).

    Raises ValidationError (422) for unknown ids — the caller decides whether to
    surface it at creation time; the mapper never silently falls back.
    """
    wid = workflow_id or DEFAULT_WORKFLOW_ID
    filename = _resolve_catalog(workflows_dir).get(wid)
    if filename is None:
        raise ValidationError(
            "Unknown workflow template.",
            {"workflow_id": wid, "supported": sorted(_resolve_catalog(workflows_dir))},
        )
    base = workflows_dir or settings.workflows_dir
    return base / filename


class WorkflowMapper:
    """Template loader + placeholder injector for ONE workflow id."""

    def __init__(
        self,
        workflow_id: str | None = None,
        workflows_dir: Path | None = None,
        schema: WorkflowSchema | None = None,
    ) -> None:
        self.workflow_id = workflow_id or DEFAULT_WORKFLOW_ID
        self.workflow_path = resolve_workflow_path(self.workflow_id, workflows_dir)
        self.schema = schema or _default_schema()
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
        """P1-E2-T01 + P4-T005: fail fast on missing output node / schema contract."""
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

        # P4-T005: schema-driven template contract (unknown tokens + required
        # placeholders). A template that violates the schema is a provider-side defect,
        # so surface it as ComfyUIError (preflight/test-connection also catch this type).
        try:
            self.schema.validate_template(template)
        except ValidationError as exc:
            raise ComfyUIError(exc.message, {"workflow_id": self.workflow_id, **exc.details}) from exc

    def build(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        seed: int | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_images: list[str] | None = None,
        checkpoint: str | None = None,
    ) -> dict:
        """Return a workflow with placeholders substituted from the schema
        (reference upload is the caller's job). Parameters are type/range validated
        via the schema; errors surface as ValidationError (422)."""
        template = self.load_template()
        # P4-T006: the mapper no longer hand-writes a values dict — the schema owns
        # the logical-name → placeholder mapping, defaults and random-seed resolution.
        values = self.schema.coerce(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            width=width,
            height=height,
            reference_images=reference_images,
            checkpoint=checkpoint,
        )

        workflow = json.loads(json.dumps(template))  # deep copy
        for node in workflow.values():
            inputs = node.get("inputs", {})
            for key, value in list(inputs.items()):
                if isinstance(value, str) and value in values:
                    inputs[key] = values[value]
        return workflow
