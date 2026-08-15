"""WorkflowProviderAdapter (P4-T001).

The business layer (generation_service / worker) must obtain a workflow only through
this adapter interface — it never touches the template directory or ComfyUI internals
directly (red line: external implementations are reached via Studio Domain Contract).

The adapter wraps the existing read-only ComfyUI WorkflowMapper (providers/comfyui/
workflow_mapper.py) behind three operations:

  - resolve(workflow_id): canonical id -> template path (unknown id -> 422)
  - build(request): placeholder-inject the resolved template from logical params
  - preflight(workflow_id): validate a template without building

The ComfyUI concretization lives in ComfyUIWorkflowProviderAdapter; business code
composes against the abstract WorkflowProviderAdapter Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.providers.image.base import ImageRequest


@dataclass
class WorkflowBuildInput:
    """Logical (domain) parameters for a workflow — never ComfyUI node ids."""

    prompt: str
    negative_prompt: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    reference_images: list[str] = field(default_factory=list)

    @classmethod
    def from_image_request(cls, request: ImageRequest) -> WorkflowBuildInput:
        """Adapt an ImageRequest into logical workflow build params (contract §7)."""
        return cls(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            width=request.width,
            height=request.height,
            reference_images=list(request.reference_images or []),
        )


@dataclass
class WorkflowPreflightResult:
    """Outcome of preflighting a workflow template."""

    workflow_id: str
    ok: bool
    output_node_id: str | None = None
    error: str | None = None
    error_code: str | None = None


@runtime_checkable
class WorkflowProviderAdapter(Protocol):
    """Interface the business layer uses to obtain built ComfyUI workflows."""

    def resolve(self, workflow_id: str | None = None) -> Path:
        """Map a canonical workflow_id to its template path (unknown -> 422)."""
        ...

    def build(self, request: WorkflowBuildInput, workflow_id: str | None = None) -> dict:
        """Return a provider-ready workflow dict from logical params."""
        ...

    def preflight(self, workflow_id: str | None = None) -> WorkflowPreflightResult:
        """Validate a template without building; never raises to the caller."""
        ...
