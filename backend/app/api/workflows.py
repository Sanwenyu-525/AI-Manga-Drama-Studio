"""Workflow API (read-only): template catalog + immutable version snapshots.

Serves the local ComfyUI workflow templates (workflows/*.json, API format) from the
registered catalog (WorkflowService): id, template file, node inventory and placeholder
tokens. Editing/uploading templates is out of scope (YAGNI — a directory scan + hash
snapshot is enough). The Router holds no business logic.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import NotFoundError
from app.domain.workflow import WorkflowTemplateRead, WorkflowVersionRead
from app.providers.comfyui.workflow_mapper import resolve_workflow_path
from app.services import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowTemplateRead])
def list_workflows(db: Session = Depends(get_db)) -> list[WorkflowTemplateRead]:
    """Catalog of registered workflow templates (backward compatible shape)."""
    return WorkflowService(db).list_templates()


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionRead])
def list_workflow_versions(workflow_id: str, db: Session = Depends(get_db)) -> list[WorkflowVersionRead]:
    """Immutable version snapshots for a workflow_id (SHA-256 file hash)."""
    # Existence + preflight validation lives in the Service/resolver, not here.
    resolve_workflow_path(workflow_id)  # unknown id -> ValidationError (422)
    items = WorkflowService(db).list_versions(workflow_id)
    if not items:
        raise NotFoundError("Workflow has no registered versions.", {"workflow_id": workflow_id})
    return items
