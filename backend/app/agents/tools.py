"""Agent tools (agent-director §28-32, mvp-spec §80): LangChain tools wrapping Studio Services.

Strict rules (red lines):
- Tools NEVER touch SQL/storage/ComfyUI directly — they call Application Services.
- Arguments/results are strictly structured (Pydantic) — no free-text parameters.
- The executor calls these deterministically from the graph (no LLM tool-calling loop needed).
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, StudioError
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


class UpdateSceneArgs(BaseModel):
    """自主迭代 07：场景级修改（时段/光照/天气/氛围/描述/名称）。

    scene_id 由 planner 从 selection.scene_id 解析；patch 白名单与
    SceneUpdate 一致（后端 update_scene 触发 P8-T017 连续性重算 + stale 标记）。
    """

    scene_id: str
    patch: dict = Field(
        ...,
        description="Valid keys: name, time_of_day, lighting, weather, mood, description",
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


class CheckWorkflowArgs(BaseModel):
    """P2-E4-T02 检查通道: live-validate a workflow template against the connected
    ComfyUI (missing nodes / missing models / broken links). workflow_id omitted →
    the system default template."""

    workflow_id: str | None = None


class InspectComfyArgs(BaseModel):
    """P2-E4-T02 检查通道: read-only ComfyUI environment summary (reachability,
    node count, workflow list, introspection source). No arguments."""


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
    "update_scene": UpdateSceneArgs,
    "generate_image": GenerateImageArgs,
    "continuity_fix": ContinuityFixArgs,
    "check_workflow": CheckWorkflowArgs,
    "inspect_comfy": InspectComfyArgs,
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
        """R1 (P2-E3-T02): update_shot is a reversible edit — it AUTO-APPLIES through
        ShotService (never raw ORM) and records an undoable ChangeSet (P2-E3-T03),
        so the default flow is not interrupted by confirmation fatigue. If the risk
        policy escalates it to approval (risk.py), it falls back to the P7 proposal
        path: a pending AgentProposal, run WAITING_HUMAN, apply on human approve.

        Idempotent on graph resume: LangGraph re-executes the whole execute node
        after an interrupt — an identical agent change set for (run, shot) means
        this step already applied in the pre-interrupt pass, so it is skipped.
        """
        from app.agents.risk import approval_needed, classify_tool_operation

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
        assessment = classify_tool_operation("update_shot", args)
        if approval_needed("update_shot", args):
            return self._update_shot_via_proposal(run, shot, requested, assessment)

        # Already applied by this run in the pre-interrupt pass? (resume re-run)
        existing = self._existing_agent_change_set(run.id, shot.id, "update_shot")
        if existing is not None:
            after = json.loads(existing.after_json) if existing.after_json else {}
            if after == requested:
                return ToolResult(
                    success=True,
                    entity_id=shot.id,
                    changed_fields=list(requested),
                    data={"message": "already applied", "change_set_id": existing.id, "revision": existing.revision_after},
                )
        from app.domain.shot import ShotUpdate
        from app.services.change_set_service import ChangeSetService

        patch = ShotUpdate.model_validate(requested)
        before = self.shots.get_shot(shot.id)  # user-visible before values (read DTO)
        try:
            updated = self.shots.update_shot(
                shot.id,
                shot.revision,
                patch,
                source="agent",
                run_id=run.id,
            )
        except ConflictError as exc:
            return ToolResult(success=False, error=exc.message, data={"code": exc.code})
        change_set = ChangeSetService(self.session).record_shot_patch(
            project_id=run.project_id,
            run_id=run.id,
            tool="update_shot",
            shot_id=shot.id,
            before={f: getattr(before, f, None) for f in requested},
            after={f: getattr(updated, f, None) for f in requested},
            revision_before=before.revision,
            revision_after=updated.revision,
        )
        return ToolResult(
            success=True,
            entity_id=shot.id,
            changed_fields=list(requested),
            data={
                "applied": True,
                "change_set_id": change_set.id,
                "revision": updated.revision,
                "risk_level": assessment.risk_level,
            },
        )

    def _update_shot_via_proposal(self, run, shot, requested: dict, assessment) -> ToolResult:
        """Escalated update path (risk policy): pending proposal + WAITING_HUMAN."""
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
            assessment=assessment,
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
                "risk_level": assessment.risk_level,
            },
        )

    def _existing_shot_proposal(self, run_id: str, shot_id: str):
        """The latest update_shot proposal for (run, target) — used to avoid proposing
        twice when execute_node re-runs after a resume."""
        return self._existing_proposal(run_id, shot_id, "update_shot")

    def _existing_proposal(self, run_id: str, shot_id: str, tool: str):
        """The latest proposal for (run, target, tool) — any status: a decided
        proposal means the human decision already happened (approve applied or
        reject skipped), so a resume re-run must not re-propose."""
        from sqlalchemy import select

        from app.db.models import AgentProposal

        return self.session.scalar(
            select(AgentProposal)
            .where(
                AgentProposal.run_id == run_id,
                AgentProposal.target_id == shot_id,
                AgentProposal.tool == tool,
            )
            .order_by(AgentProposal.created_at.desc())
            .limit(1)
        )

    def _existing_agent_change_set(self, run_id: str, shot_id: str, tool: str):
        """The latest agent change set for (run, target, tool) — an identical patch
        means the auto-apply already ran in the pre-interrupt pass (resume re-run)."""
        from sqlalchemy import select

        from app.db.models import AgentChangeSet

        return self.session.scalar(
            select(AgentChangeSet)
            .where(
                AgentChangeSet.run_id == run_id,
                AgentChangeSet.entity_id == shot_id,
                AgentChangeSet.tool == tool,
                AgentChangeSet.source == "agent",
            )
            .order_by(AgentChangeSet.created_at.desc())
            .limit(1)
        )

    def _update_scene(self, args: dict) -> ToolResult:
        """自主迭代 07：R1 可逆编辑——场景环境/名称修改自动应用（走 SceneService，
        触发 P8-T017 连续性重算 + stale 标记），并记录 scene ChangeSet（可撤销）。

        scene_id 由 planner 从 selection.scene_id 解析；ownership 由 _require_scene
        复核。幂等：resume 重跑 execute_node 时，相同 (run, scene, tool) 的 agent
        change set 已存在且 after 一致 → 跳过。
        """
        from app.agents.risk import approval_needed, classify_tool_operation

        schema = UpdateSceneArgs.model_validate(args)
        scene = self._require_scene(schema.scene_id)
        requested = {key: value for key, value in schema.patch.items() if value is not None}
        if not requested:
            return ToolResult(
                success=True,
                entity_id=scene.id,
                changed_fields=[],
                data={"applied": False, "message": "no change requested"},
            )
        run = self.session.get(AgentRun, self.run_id) if self.run_id else None
        if run is None:
            return ToolResult(
                success=False,
                error="update_scene requires a persisted agent run.",
                data={"code": "AGENT_RUN_REQUIRED"},
            )
        assessment = classify_tool_operation("update_scene", args)
        if approval_needed("update_scene", args):
            # update_scene 恒 R1（自动应用）；此分支仅防未来风险策略升级——未知
            # 风险宁可拒绝也不猜测（红线：不静默写库）。
            return ToolResult(
                success=False,
                error="update_scene risk escalated; manual approval not implemented.",
                data={"code": "RISK_ESCALATED", "risk_level": assessment.risk_level},
            )

        existing = self._existing_agent_change_set(run.id, scene.id, "update_scene")
        if existing is not None:
            after = json.loads(existing.after_json) if existing.after_json else {}
            if after == requested:
                return ToolResult(
                    success=True,
                    entity_id=scene.id,
                    changed_fields=list(requested),
                    data={"message": "already applied", "change_set_id": existing.id, "revision": existing.revision_after},
                )
        from app.domain.scene import SceneUpdate
        from app.services.change_set_service import ChangeSetService
        from app.services.scene_service import SceneService

        patch = SceneUpdate.model_validate(requested)
        scenes = SceneService(self.session)
        before = scenes.get_scene(scene.id)
        try:
            updated = scenes.update_scene(scene.id, scene.revision, patch)
        except ConflictError as exc:
            return ToolResult(success=False, error=exc.message, data={"code": exc.code})
        change_set = ChangeSetService(self.session).record_scene_patch(
            project_id=run.project_id,
            run_id=run.id,
            tool="update_scene",
            scene_id=scene.id,
            before={f: getattr(before, f, None) for f in requested},
            after={f: getattr(updated, f, None) for f in requested},
            revision_before=before.revision,
            revision_after=updated.revision,
        )
        return ToolResult(
            success=True,
            entity_id=scene.id,
            changed_fields=list(requested),
            data={
                "applied": True,
                "change_set_id": change_set.id,
                "revision": updated.revision,
                "risk_level": assessment.risk_level,
            },
        )

    def _generate_image(self, args: dict) -> ToolResult:
        """R2 (P2-E3-T02): generation is expensive — by default NO Generation row is
        created before a human approves a pending proposal carrying the risk
        metadata (affected shot, task count, cost=unknown for local providers).
        With STUDIO_AGENT_AUTO_APPROVE_R2=true (dev/demo) it queues directly."""
        from app.agents.risk import approval_needed, classify_tool_operation

        schema = GenerateImageArgs.model_validate(args)
        shot = self._require_shot(schema.shot_id)
        run = self.session.get(AgentRun, self.run_id) if self.run_id else None
        if run is None:
            return ToolResult(
                success=False,
                error="generate_image requires a persisted agent run.",
                data={"code": "AGENT_RUN_REQUIRED"},
            )
        assessment = classify_tool_operation("generate_image", args)

        # Idempotent on graph resume — LangGraph re-executes the whole execute
        # node after an interrupt. Two cases mean this step already ran:
        # 1) a generation already queued by THIS run for this shot (approved), or
        # 2) a generate_image proposal already exists for this run+target (decided
        #    or pending) — a rejected/expired proposal must not re-propose.
        existing_generation = self._existing_run_generation(run.id, schema.shot_id)
        if existing_generation is not None:
            return ToolResult(
                success=True,
                entity_id=existing_generation.id,
                created_entities=[existing_generation.id],
                data={"generation_id": existing_generation.id, "status": existing_generation.status, "message": "already queued"},
            )
        existing_proposal = self._existing_proposal(run.id, schema.shot_id, "generate_image")
        if existing_proposal is not None:
            return ToolResult(
                success=True,
                entity_id=shot.id,
                proposal_created=False,
                proposal_id=existing_proposal.id,
                data={
                    "proposal_id": existing_proposal.id,
                    "status": existing_proposal.status,
                    "message": "already decided",
                },
            )

        if approval_needed("generate_image", args):
            proposal = ProposalService(self.session).create_generation_proposal(
                run,
                shot.id,
                shot.revision,
                {
                    "prompt": schema.prompt,
                    "seed": schema.seed,
                    "width": schema.width,
                    "height": schema.height,
                },
                assessment,
            )
            return ToolResult(
                success=True,
                entity_id=shot.id,
                proposal_created=True,
                proposal_id=proposal.id,
                data={
                    "proposal_id": proposal.id,
                    "status": "pending",
                    "risk_level": assessment.risk_level,
                    "estimated_tasks": assessment.estimated_tasks,
                    "message": "generation awaits approval",
                },
            )

        from app.domain.generation import GenerationCreate

        generation = self.generations.create_generation(
            schema.shot_id,
            GenerationCreate(type="image", prompt=schema.prompt, seed=schema.seed, width=schema.width, height=schema.height),
            run_id=run.id,
        )
        return ToolResult(
            success=True,
            entity_id=generation.id,
            created_entities=[generation.id],
            data={"generation_id": generation.id, "status": generation.status, "risk_level": assessment.risk_level},
        )

    def _existing_run_generation(self, run_id: str, shot_id: str):
        """A generation already queued by this run for this shot (resume idempotency)."""
        from sqlalchemy import select

        from app.db.models import Generation

        return self.session.scalar(
            select(Generation)
            .where(Generation.run_id == run_id, Generation.shot_id == shot_id)
            .order_by(Generation.created_at.desc())
            .limit(1)
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

    # --- 检查通道工具（P2-E4-T02，R0 只读；经 WorkflowDiagnosticsService 红线合规） ---

    def _check_workflow(self, args: dict) -> ToolResult:
        """Live-validate a workflow template against the connected ComfyUI."""
        schema = CheckWorkflowArgs.model_validate(args)
        from app.services.workflow_diagnostics_service import get_workflow_diagnostics_service

        diagnostics = get_workflow_diagnostics_service().validate_workflow_sync(schema.workflow_id)
        data = diagnostics.to_dict()
        if diagnostics.status == "invalid":
            summary = "workflow 不可运行：" + "；".join(
                filter(None, [
                    f"缺节点 {', '.join(diagnostics.missing_nodes)}" if diagnostics.missing_nodes else "",
                    f"缺模型 {', '.join(diagnostics.missing_models[:5])}" if diagnostics.missing_models else "",
                    f"断链 {', '.join(diagnostics.broken_links[:5])}" if diagnostics.broken_links else "",
                ])
            )
        elif diagnostics.status == "ok":
            summary = "workflow 与当前 ComfyUI 环境完全兼容。"
        elif diagnostics.status == "unreachable":
            summary = f"无法完成 live 校验：{diagnostics.error}"
        else:
            summary = f"模板静态缺陷：{diagnostics.static_error}"
        data["summary"] = summary
        return ToolResult(success=True, entity_id=diagnostics.workflow_id, warnings=[summary], data=data)

    def _inspect_comfy(self, args: dict) -> ToolResult:
        """Read-only ComfyUI environment summary (reachability / node count / workflows)."""
        from app.core.config import settings
        from app.providers.comfyui.client import ComfyUIClient
        from app.services.workflow_diagnostics_service import get_workflow_diagnostics_service

        service = get_workflow_diagnostics_service()
        client = ComfyUIClient()
        info = service._cached(service._sync_cache, client.base_url, client.get_object_info_sync)
        from app.providers.comfyui.workflow_mapper import _resolve_catalog

        workflows = sorted(_resolve_catalog())
        if info is None:
            return ToolResult(
                success=True,
                warnings=["ComfyUI 不可达。"],
                data={
                    "reachable": False,
                    "base_url": client.base_url,
                    "workflows": workflows,
                    "introspection_mode": settings.comfy_introspection,
                },
            )
        return ToolResult(
            success=True,
            data={
                "reachable": True,
                "base_url": client.base_url,
                "node_count": len(info),
                "workflows": workflows,
                "introspection_mode": settings.comfy_introspection,
                "summary": f"ComfyUI 可达，已安装 {len(info)} 个节点类。",
            },
        )
