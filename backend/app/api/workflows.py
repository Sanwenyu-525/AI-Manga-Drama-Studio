"""Workflow API (read-only): list the workflow template catalog with preflight metadata.

Serves the local ComfyUI workflow templates (workflows/*.json, API format) as a
read-only catalog — id, template file, node inventory and placeholder tokens.
Editing/uploading templates is out of MVP scope (mvp-spec §66-67: templates are
checked into the repo)."""
from __future__ import annotations

import json

from fastapi import APIRouter

from app.providers.comfyui.workflow_mapper import (
    DEFAULT_WORKFLOW_ID,
    OUTPUT_NODE_CLASS,
    REQUIRED_PLACEHOLDERS,
    WORKFLOW_CATALOG,
    resolve_workflow_path,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("")
def list_workflows() -> list[dict]:
    """Catalog of workflow templates: id → file + structural metadata."""
    items: list[dict] = []
    for wid, filename in WORKFLOW_CATALOG.items():
        path = resolve_workflow_path(wid)
        meta: dict = {
            "id": wid,
            "file": filename,
            "is_default": wid == DEFAULT_WORKFLOW_ID,
            "output_node_class": OUTPUT_NODE_CLASS,
            "required_placeholders": list(REQUIRED_PLACEHOLDERS),
            "exists": path.exists(),
        }
        if path.exists():
            try:
                template = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                meta["valid_json"] = False
                items.append(meta)
                continue
            meta["valid_json"] = True
            meta["node_count"] = len(template)
            class_types = [node.get("class_type") for node in template.values() if isinstance(node, dict)]
            meta["node_types"] = sorted(set(c for c in class_types if c))
            tokens: set[str] = set()
            for node in template.values():
                if not isinstance(node, dict):
                    continue
                for value in node.get("inputs", {}).values():
                    if isinstance(value, str) and value.startswith("$"):
                        tokens.add(value)
            meta["placeholder_tokens"] = sorted(tokens)
        items.append(meta)
    return items
