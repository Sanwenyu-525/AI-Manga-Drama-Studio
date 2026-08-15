"""Workflow catalog DTOs (P4-T004, api-event-contract §48.1).

The WorkflowService snapshots the local ComfyUI template directory (workflows/*.json)
into workflow_templates + workflow_versions, and exposes a read-only catalog that
stays backward compatible with the original GET /api/v1/workflows shape.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WorkflowTemplateRead(BaseModel):
    """Template list item — keeps the legacy catalog fields (id == workflow_id)
    plus template-level metadata derived from the DB + parsed JSON file."""

    id: str  # workflow_id (compat)
    file: str | None
    is_default: bool
    workflow_type: str = "image"
    name: str | None = None
    template_id: str | None = None  # ORM template pk
    active_version_number: int | None = None
    file_hash: str | None = None
    output_node_class: str | None = None
    required_placeholders: list[str] = []
    exists: bool = False
    valid_json: bool = False
    node_count: int | None = None
    node_types: list[str] = []
    placeholder_tokens: list[str] = []
    node_metadata: dict[str, Any] = {}


class WorkflowVersionRead(BaseModel):
    """Immutable file-hash snapshot row."""

    id: str
    template_id: str
    workflow_id: str | None = None
    version_number: int
    file_hash: str
    file_path: str
    status: str
    created_at: str
