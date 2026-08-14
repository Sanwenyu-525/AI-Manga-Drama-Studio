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
    """Deterministic executor for ToolOperation lists (agent-director §27, §70)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.shots = ShotService(session)
        self.generations = GenerationService(session)
        self.context = ContextService(session)

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
        shot = self.shots.get_shot(schema.shot_id)
        return ToolResult(success=True, entity_id=shot.id, data=shot.model_dump())

    def _get_scene_shots(self, args: dict) -> ToolResult:
        schema = GetSceneShotsArgs.model_validate(args)
        shots = self.shots.list_shots(schema.scene_id)
        return ToolResult(
            success=True,
            entity_id=schema.scene_id,
            data={"shots": [s.model_dump() for s in shots]},
        )

    def _update_shot(self, args: dict) -> ToolResult:
        schema = UpdateShotArgs.model_validate(args)
        shot = self.shots.get_shot(schema.shot_id)
        from app.domain.shot import ShotUpdate, ShotUpdateRequest

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
