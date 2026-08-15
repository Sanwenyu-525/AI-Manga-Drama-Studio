"""WorkflowResolver (P4-T007) — resolve the workflow_id for a generation request.

Priority chain:
  1. request override  → an explicit generation.workflow_id wins.
  2. project default   → project_settings.default_image_workflow_id (image) or
                         default_video_workflow_id (video), when set.
  3. system default    → workflows/default_image_api.json (WORKFLOW_CATALOG default).

Every resolved id is validated against the canonical WORKFLOW_CATALOG (via
resolve_workflow_path); an unknown override or project default is a 422, never a silent
fallback (consistent with the "no silent fallback" invariant in P1-E2-T01).

Business logic lives in the Service layer — the Router never resolves workflows itself.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.db.models import ProjectSetting
from app.providers.comfyui.workflow_mapper import (
    DEFAULT_WORKFLOW_ID as SYSTEM_DEFAULT_WORKFLOW_ID,
    resolve_workflow_path,
)

logger = get_logger("workflows.resolver")

# project_settings field that selects the default workflow per generation type.
TYPE_TO_SETTING_FIELD = {
    "image": "default_image_workflow_id",
    "video": "default_video_workflow_id",
}


def _validate(workflow_id: str) -> str:
    """Canonical-id check (422 on unknown); returns the valid id."""
    path = resolve_workflow_path(workflow_id)  # raises ValidationError (422)
    if not path.exists():
        raise ValidationError(
            "Workflow template file does not exist.",
            {"workflow_id": workflow_id, "path": str(path)},
        )
    return workflow_id


class WorkflowResolver:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def resolve(
        self,
        generation_type: str,
        *,
        request_workflow_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Return the resolved workflow_id following the priority chain.

        - request_workflow_id: explicit override (validated, 422 if unknown).
        - project_id: read the project's default_<type>_workflow_id when set.
        - otherwise: the system default workflow.
        """
        if request_workflow_id:
            return _validate(request_workflow_id)

        if project_id and self.session is not None:
            field = TYPE_TO_SETTING_FIELD.get(generation_type)
            if field:
                project_default = self._load_project_default(project_id, field)
                if project_default:
                    return _validate(project_default)

        # system default — resolve_workflow_path(None) returns DEFAULT_WORKFLOW_ID path.
        resolve_workflow_path(SYSTEM_DEFAULT_WORKFLOW_ID)
        return SYSTEM_DEFAULT_WORKFLOW_ID

    def _load_project_default(self, project_id: str, field: str) -> str | None:
        """Return the project's configured default workflow id, if any."""
        row = self.session.get(ProjectSetting, project_id)
        if row is None:
            return None
        value = getattr(row, field, None)
        return value if isinstance(value, str) and value else None
