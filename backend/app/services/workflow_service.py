"""WorkflowService (P4-T004) — read-only catalog registry.

Snapshots the local ComfyUI template directory (settings.workflows_dir/*.json) into
workflow_templates + immutable workflow_versions (SHA-256 file hash). The Router only
serves what this service has registered — registration is idempotent ("scan + upsert").

YAGNI: no editor / upload / diff tooling. A directory scan + hash snapshot is enough
to power the resolver, the catalog API and the versions list.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import WorkflowTemplate, WorkflowVersion
from app.domain.workflow import WorkflowTemplateRead, WorkflowVersionRead
from app.providers.comfyui.workflow_mapper import (
    DEFAULT_WORKFLOW_ID,
    OUTPUT_NODE_CLASS,
    REQUIRED_PLACEHOLDERS,
    resolve_workflow_path,
)
from app.repositories import WorkflowTemplateRepository, WorkflowVersionRepository

logger = get_logger("workflows")

DEFAULT_WORKFLOW_TYPE_MAP = {
    "default_image_api": "image",
}


def _infer_workflow_type(workflow_id: str, filename: str) -> str:
    """Best-effort type inference: filename keyword wins, then defaults to image."""
    lower = filename.lower()
    if "video" in lower:
        return "video"
    return DEFAULT_WORKFLOW_TYPE_MAP.get(workflow_id, "image")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class WorkflowService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.templates = WorkflowTemplateRepository(session)
        self.versions = WorkflowVersionRepository(session)

    # --- registration (idempotent scan + upsert) ---

    def ensure_registered(self) -> int:
        """Scan settings.workflows_dir for *.json templates and idempotently upsert
        each as a template + version snapshot. Returns the number of templates touched.

        A template whose disk hash changed vs. its active version is upserted as a
        NEW version (immutable history) and activated.
        """
        touched = 0
        for path in sorted(settings.workflows_dir.glob("*.json")):
            workflow_id = path.stem
            wtype = _infer_workflow_type(workflow_id, path.name)
            file_hash = _sha256(path)
            template = self.templates.by_workflow_id(workflow_id, wtype)
            if template is None:
                template = WorkflowTemplate(
                    name=workflow_id,
                    workflow_type=wtype,
                    workflow_id=workflow_id,
                )
                self.session.add(template)
                self.session.flush()
                version = WorkflowVersion(
                    template_id=template.id,
                    version_number=1,
                    file_hash=file_hash,
                    file_path=path.name,
                    status="active",
                )
                self.session.add(version)
                self.session.flush()
                template.active_version_id = version.id
                touched += 1
                logger.info("registered workflow template %s (v1)", workflow_id)
                continue

            active = self.versions.latest_for_template(template.id)
            if active is not None and active.file_hash == file_hash:
                continue  # unchanged — idempotent no-op

            version_number = (active.version_number if active else 0) + 1
            version = WorkflowVersion(
                template_id=template.id,
                version_number=version_number,
                file_hash=file_hash,
                file_path=path.name,
                status="active",
            )
            self.session.add(version)
            if active is not None:
                active.status = "superseded"
            self.session.flush()
            template.active_version_id = version.id
            template.updated_at = datetime.now(UTC).isoformat()
            touched += 1
            logger.info("workflow %s template changed -> v%d", workflow_id, version_number)
        self.session.commit()
        return touched

    # --- queries ---

    def list_templates(self) -> list[WorkflowTemplateRead]:
        """Backward-compatible catalog (id == workflow_id) backed by registered templates."""
        self.ensure_registered()
        items: list[WorkflowTemplateRead] = []
        for template in self.templates.list_all():
            items.append(self._to_read(template, resolve_path=True))
        return items

    def list_versions(self, workflow_id: str) -> list[WorkflowVersionRead]:
        """Version snapshots for a workflow_id (the JSON file id / template)."""
        self.ensure_registered()
        template = self.templates.by_workflow_id(workflow_id, _infer_workflow_type(workflow_id, f"{workflow_id}.json"))
        if template is None:
            return []
        rows = self.versions.list_for_template(template.id)
        return [
            WorkflowVersionRead(
                id=v.id,
                template_id=v.template_id,
                workflow_id=workflow_id,
                version_number=v.version_number,
                file_hash=v.file_hash,
                file_path=v.file_path,
                status=v.status,
                created_at=v.created_at,
            )
            for v in rows
        ]

    def get_template(self, workflow_id: str) -> WorkflowTemplate | None:
        self.ensure_registered()
        return self.templates.by_workflow_id(workflow_id, _infer_workflow_type(workflow_id, f"{workflow_id}.json"))

    # --- read DTO helpers ---

    def _to_read(self, template: WorkflowTemplate, *, resolve_path: bool = True) -> WorkflowTemplateRead:
        path = resolve_workflow_path(template.workflow_id) if resolve_path else None
        is_default = template.workflow_id == DEFAULT_WORKFLOW_ID
        active_version = (
            self.versions.latest_for_template(template.id)
        )
        node_meta: dict = {"output_node_class": OUTPUT_NODE_CLASS, "required_placeholders": list(REQUIRED_PLACEHOLDERS)}
        exists = False
        valid_json = False
        node_count = None
        node_types: list[str] = []
        placeholder_tokens: list[str] = []
        if path is not None and path.exists():
            exists = True
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                valid_json = True
                node_count = len(data)
                class_types = [node.get("class_type") for node in data.values() if isinstance(node, dict)]
                node_types = sorted({c for c in class_types if c})
                for node in data.values():
                    if not isinstance(node, dict):
                        continue
                    for value in node.get("inputs", {}).values():
                        if isinstance(value, str) and value.startswith("$"):
                            placeholder_tokens.append(value)
                placeholder_tokens = sorted(set(placeholder_tokens))
            except json.JSONDecodeError:
                valid_json = False
                node_meta["error"] = "invalid_json"
        return WorkflowTemplateRead(
            id=template.workflow_id,
            file=path.name if path else None,
            is_default=is_default,
            workflow_type=template.workflow_type,
            name=template.name,
            template_id=template.id,
            active_version_number=active_version.version_number if active_version else None,
            file_hash=active_version.file_hash if active_version else None,
            output_node_class=node_meta["output_node_class"],
            required_placeholders=list(node_meta["required_placeholders"]),
            exists=exists,
            valid_json=valid_json,
            node_count=node_count,
            node_types=node_types,
            placeholder_tokens=placeholder_tokens,
            node_metadata=node_meta,
        )
