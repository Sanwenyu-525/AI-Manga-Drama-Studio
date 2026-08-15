"""Agent tools (agent-director §28-32, mvp-spec §80): LangChain tools wrapping Studio Services.

Strict rules (red lines):
- Tools NEVER touch SQL/storage/ComfyUI directly — they call Application Services.
- Arguments/results are strictly structured (Pydantic) — no free-text parameters.
- The executor calls these deterministically from the graph (no LLM tool-calling loop needed).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import StudioError
from app.domain.agent import ToolOperation
from app.domain.common import DirtyState, ShotStatus, ShotType
from app.services.context_service import ContextService
from app.services.generation_service import GenerationService
from app.services.shot_service import ShotService


class GetShotArgs(BaseModel):
    shot_id: str


class GetSceneShotsArgs(BaseModel):
    scene_id: str


class UpdateShotArgs(BaseModel):
    shot_id: str
    patch: dict = Field(
        ...,
        description="Valid keys: shot_type, camera_angle, camera_movement, duration, action, emotion, dialogue, image_prompt, status, dirty_state",
    )


class GenerateImageArgs(BaseModel):
    shot_id: str
    prompt: str | None = None
    seed: int | None = None
    width: int | None = None
    height: int | None = None


class ToolResult(BaseModel):
    """Unified tool result (agent-director §32): never free-form natural language."""

    success: bool
    entity_id: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    created_entities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    data: dict | None = None


# Tool schemas keyed by tool name (validation + documentation, agent-director §31).
TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_shot": GetShotArgs,
    "get_scene_shots": GetSceneShotsArgs,
    "update_shot": UpdateShotArgs,
    "generate_image": GenerateImageArgs,
}


class ToolExecutor:
    """Deterministic executor for ToolOperation lists (agent-director §27, §70).

    P1-E3-T01 (defense in depth): the executor never trusts the planner alone —
    every target shot/scene is re-validated (live + owned by the run's project)
    right before the tool runs, so a hallucinated or forged id is rejected.
    """

    def __init__(
        self,
        session: Session,
        *,
        project_id: str | None = None,
        resolved_shot_id: str | None = None,
    ) -> None:
        self.session = session
        self.project_id = project_id
        self.resolved_shot_id = resolved_shot_id
        self.shots = ShotService(session)
        self.generations = GenerationService(session)
        self.context = ContextService(session)

    # --- ownership defense (P1-E3-T01) ---

    def _require_shot(self, shot_id: str):
        """Reject missing/deleted shots and shots outside the run's project."""
        from app.core.errors import ValidationError
        from app.db.models import Episode, Scene, Shot

        shot = self.session.get(Shot, shot_id)
        if shot is None or shot.deleted_at:
            raise ValidationError("Shot does not exist or was deleted.", {"shot_id": shot_id})
        if self.project_id:
            scene = self.session.get(Scene, shot.scene_id)
            episode = self.session.get(Episode, scene.episode_id) if scene else None
            if episode is None or episode.project_id != self.project_id:
                raise ValidationError(
                    "Shot does not belong to the run's project.",
                    {"shot_id": shot_id, "project_id": self.project_id},
                )
        return shot

    def _require_scene(self, scene_id: str):
        """Reject missing/deleted scenes and scenes outside the run's project."""
        from app.core.errors import ValidationError
        from app.db.models import Episode, Scene

        scene = self.session.get(Scene, scene_id)
        if scene is None or scene.deleted_at:
            raise ValidationError("Scene does not exist or was deleted.", {"scene_id": scene_id})
        if self.project_id:
            episode = self.session.get(Episode, scene.episode_id)
            if episode is None or episode.project_id != self.project_id:
                raise ValidationError(
                    "Scene does not belong to the run's project.",
                    {"scene_id": scene_id, "project_id": self.project_id},
                )
        return scene

    def execute(self, op: ToolOperation) -> ToolResult:
        try:
            handler = getattr(self, f"_{op.tool}")
            return handler(op.arguments)
        except StudioError as exc:
            return ToolResult(success=False, error=exc.message, data={"code": exc.code})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

    # --- tool implementations (→ Services only) ---

    def _get_shot(self, args: dict) -> ToolResult:
        schema = GetShotArgs.model_validate(args)
        shot = self._require_shot(schema.shot_id)
        return ToolResult(success=True, entity_id=shot.id, data=self.shots.get_shot(shot.id).model_dump())

    def _get_scene_shots(self, args: dict) -> ToolResult:
        schema = GetSceneShotsArgs.model_validate(args)
        self._require_scene(schema.scene_id)
        shots = self.shots.list_shots(schema.scene_id)
        return ToolResult(
            success=True,
            entity_id=schema.scene_id,
            data={"shots": [s.model_dump() for s in shots]},
        )

    def _update_shot(self, args: dict) -> ToolResult:
        schema = UpdateShotArgs.model_validate(args)
        shot = self._require_shot(schema.shot_id)
        from app.domain.shot import ShotUpdate

        patch = ShotUpdate.model_validate(schema.patch)
        updated = self.shots.update_shot(schema.shot_id, shot.revision, patch)
        return ToolResult(
            success=True,
            entity_id=updated.id,
            changed_fields=list(schema.patch.keys()),
            data=updated.model_dump(),
        )

    def _generate_image(self, args: dict) -> ToolResult:
        schema = GenerateImageArgs.model_validate(args)
        self._require_shot(schema.shot_id)
        from app.domain.generation import GenerationCreate

        generation = self.generations.create_generation(
            schema.shot_id,
            GenerationCreate(type="image", prompt=schema.prompt, seed=schema.seed, width=schema.width, height=schema.height),
        )
        return ToolResult(
            success=True,
            entity_id=generation.id,
            created_entities=[generation.id],
            data={"generation_id": generation.id, "status": generation.status},
        )
