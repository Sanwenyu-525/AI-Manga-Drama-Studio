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
from app.db.models import AgentRun
from app.services.context_service import ContextService
from app.services.generation_service import GenerationService
from app.services.proposal_service import ProposalService
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


class ContinuityFixArgs(BaseModel):
    """P8-T019: fix one continuity warning. patch is a shot field patch (Valid keys
    follow update_shot); shot_id is optional (resolved from the warning)."""

    warning_id: str
    shot_id: str | None = None
    patch: dict = Field(
        default_factory=dict,
        description="Valid keys: shot_type, camera_angle, camera_movement, duration, action, emotion, dialogue, image_prompt, status, dirty_state",
    )


class ToolResult(BaseModel):
    """Unified tool result (agent-director §32): never free-form natural language."""

    success: bool
    entity_id: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    created_entities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    data: dict | None = None
    # P7-T013: update_shot now emits a Proposal instead of writing directly.
    proposal_created: bool = False
    proposal_id: str | None = None


# Tool schemas keyed by tool name (validation + documentation, agent-director §31).
TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_shot": GetShotArgs,
    "get_scene_shots": GetSceneShotsArgs,
    "update_shot": UpdateShotArgs,
    "generate_image": GenerateImageArgs,
    "continuity_fix": ContinuityFixArgs,
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
        run_id: str | None = None,
    ) -> None:
        self.session = session
        self.project_id = project_id
        self.resolved_shot_id = resolved_shot_id
        self.run_id = run_id
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
        """P7-T012/13: update_shot NO LONGER writes directly — it produces a pending
        AgentProposal; the run parks in WAITING_HUMAN and emits agent.approval.required.
        A human approves/rejects it; apply happens ONLY through ShotService (never raw
        ORM) guarded by a base_revision optimistic-concurrency check (P7-T016).

        Idempotent on graph resume: if the run already has a DECIDED proposal for this
        target, the step returns without re-creating (the human decision already
        happened), so resume re-running execute_node doesn't double-propose."""
        schema = UpdateShotArgs.model_validate(args)
        shot = self._require_shot(schema.shot_id)
        requested = {key: value for key, value in schema.patch.items() if value is not None}
        if not requested:
            return ToolResult(
                success=True,
                entity_id=shot.id,
                changed_fields=[],
                data={"proposal_created": False, "message": "no change requested"},
            )
        run = self.session.get(AgentRun, self.run_id) if self.run_id else None
        if run is None:
            return ToolResult(
                success=False,
                error="update_shot requires a persisted agent run.",
                data={"code": "AGENT_RUN_REQUIRED"},
            )
        # Already decided? (resume re-runs execute_node) — do not re-propose.
        existing = self._existing_shot_proposal(run.id, shot.id)
        if existing is not None:
            return ToolResult(
                success=True,
                entity_id=shot.id,
                changed_fields=[],
                proposal_created=False,
                proposal_id=existing.id,
                data={
                    "proposal_id": existing.id,
                    "status": existing.status,
                    "message": "already decided",
                    "base_revision": existing.base_revision,
                },
            )
        proposal = ProposalService(self.session).create_shot_proposal(
            run,
            shot.id,
            shot.revision,
            requested,
        )
        return ToolResult(
            success=True,
            entity_id=shot.id,
            changed_fields=[],
            proposal_created=True,
            proposal_id=proposal.id,
            data={
                "proposal_id": proposal.id,
                "status": "pending",
                "base_revision": shot.revision,
                "changes": requested,
            },
        )

    def _existing_shot_proposal(self, run_id: str, shot_id: str):
        """The latest proposal for (run, target) — used to avoid proposing twice when
        execute_node re-runs after a resume."""
        from sqlalchemy import select
        from app.db.models import AgentProposal

        return self.session.scalar(
            select(AgentProposal)
            .where(AgentProposal.run_id == run_id, AgentProposal.target_id == shot_id)
            .order_by(AgentProposal.created_at.desc())
            .limit(1)
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

    def _continuity_fix(self, args: dict) -> ToolResult:
        """P8-T019: create a continuity fix PROPOSAL (never a direct write). The
        proposal parks the run in WAITING_HUMAN; on human approve it applies via
        ShotService and marks the warning fixed."""
        from app.db.models import AgentRun, ContinuityWarning

        schema = ContinuityFixArgs.model_validate(args)
        warning = self.session.get(ContinuityWarning, schema.warning_id)
        if warning is None:
            return ToolResult(
                success=False,
                error="Continuity warning does not exist.",
                data={"code": "ENTITY_NOT_FOUND"},
            )
        if warning.status in ("acknowledged", "fixed"):
            return ToolResult(
                success=False,
                error="Warning is not open; no fix required.",
                data={"code": "VALIDATION_ERROR", "status": warning.status},
            )
        shot_id = schema.shot_id or warning.shot_id
        if shot_id:
            self._require_shot(shot_id)
        run = self.session.get(AgentRun, self.run_id) if self.run_id else None
        if run is None:
            return ToolResult(
                success=False,
                error="continuity_fix requires a persisted agent run.",
                data={"code": "AGENT_RUN_REQUIRED"},
            )
        proposal = ProposalService(self.session).create_continuity_fix_proposal(
            run,
            schema.warning_id,
            warning.scene_id,
            shot_id,
            schema.patch,
        )
        return ToolResult(
            success=True,
            entity_id=proposal.id,
            proposal_created=True,
            proposal_id=proposal.id,
            data={
                "proposal_id": proposal.id,
                "status": "pending",
                "target_type": proposal.target_type,
                "target_id": proposal.target_id,
                "warning_id": schema.warning_id,
            },
        )
