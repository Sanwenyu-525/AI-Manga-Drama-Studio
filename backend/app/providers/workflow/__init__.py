"""WorkflowProvider adapter family (P4-T001).

Business code reaches ComfyUI workflow templates ONLY through these adapters — never
by touching the template directory or ComfyUI internals directly.
"""

from __future__ import annotations

from app.providers.workflow.base import (
    WorkflowBuildInput,
    WorkflowPreflightResult,
    WorkflowProviderAdapter,
)
from app.providers.workflow.comfyui import ComfyUIWorkflowProviderAdapter

__all__ = [
    "WorkflowBuildInput",
    "WorkflowPreflightResult",
    "WorkflowProviderAdapter",
    "ComfyUIWorkflowProviderAdapter",
]
