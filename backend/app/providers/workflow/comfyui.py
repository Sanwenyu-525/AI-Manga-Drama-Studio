"""ComfyUIWorkflowProviderAdapter — concrete adapter over the read-only WorkflowMapper.

Self-contained: it does not mutate the mapper (which is out of scope) but delegates
resolve/build/preflight to it. Returning a WorkflowPreflightResult (never raising on
bad templates) keeps preflight a clean query for the registry / health blocks.
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import StudioError
from app.providers.comfyui.workflow_mapper import DEFAULT_WORKFLOW_ID, WorkflowMapper, resolve_workflow_path
from app.providers.workflow.base import WorkflowBuildInput, WorkflowPreflightResult


class ComfyUIWorkflowProviderAdapter:
    """WorkflowProviderAdapter impl backed by the ComfyUI template catalog."""

    name = "comfyui"

    def resolve(self, workflow_id: str | None = None) -> Path:
        return resolve_workflow_path(workflow_id)

    def build(self, request: WorkflowBuildInput, workflow_id: str | None = None) -> dict:
        mapper = WorkflowMapper(workflow_id=workflow_id)
        return mapper.build(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            width=request.width,
            height=request.height,
            reference_images=request.reference_images,
        )

    def preflight(self, workflow_id: str | None = None) -> WorkflowPreflightResult:
        try:
            mapper = WorkflowMapper(workflow_id=workflow_id)
            mapper.preflight()
            return WorkflowPreflightResult(
                workflow_id=mapper.workflow_id,
                ok=True,
                output_node_id=mapper.output_node_id,
            )
        except StudioError as exc:
            wid = workflow_id or DEFAULT_WORKFLOW_ID
            return WorkflowPreflightResult(
                workflow_id=wid,
                ok=False,
                error=exc.message,
                error_code=exc.code,
            )
