"""Agent domain schemas (agent-director-v0.1 §14, §22; api-event-contract §23-33).

The Director uses the "Structured Planner + Deterministic Executor" pattern
(agent-director §70): the LLM outputs a DirectorPlan (typed operation list),
the graph executes it deterministically through Studio Services.
"""

from typing import Literal

from pydantic import BaseModel, Field

# Agent run status constants (api-event-contract §26 + P7-T017).
RUN_STATUS_CREATED = "created"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_WAITING_APPROVAL = "waiting_approval"
RUN_STATUS_WAITING_HUMAN = "waiting_human"  # P7-T017: run suspended awaiting human decision
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_CANCELLING = "cancelling"

# Proposal status constants (design ai-director-agent §42-43, P7-T012).
PROPOSAL_STATUS_PENDING = "pending"
PROPOSAL_STATUS_APPROVED = "approved"
PROPOSAL_STATUS_REJECTED = "rejected"
PROPOSAL_STATUS_CONFLICT = "conflict"
PROPOSAL_STATUS_APPLIED = "applied"
PROPOSAL_STATUS_EXPIRED = "expired"  # P2-E3-T02: TTL elapsed, never applied

# Risk levels (agent-director §24, P2-E3-T02):
# R0 read — auto; R1 reversible edit — auto + ChangeSet; R2 expensive — approval;
# R3 destructive — approval always.
RISK_R0 = "R0"
RISK_R1 = "R1"
RISK_R2 = "R2"
RISK_R3 = "R3"
RISK_LEVELS = (RISK_R0, RISK_R1, RISK_R2, RISK_R3)


class ToolOperation(BaseModel):
    """One deterministic tool call planned by the LLM (agent-director §28-31)."""

    tool: Literal["get_shot", "update_shot", "update_scene", "generate_image", "get_scene_shots"]
    arguments: dict = Field(default_factory=dict)  # strictly typed per tool (schema in tools.py)


class ProductionIntent(BaseModel):
    """Understand node output (agent-director §13-14)."""

    intent_type: Literal["query", "create", "modify", "generate", "review", "compare", "delete", "export"]
    target_type: str | None = None  # shot | scene | episode | character | project
    target_reference: str | None = None  # "shot_005" | "第5镜" | "这个" (resolved later)
    instruction: str = ""
    batch: bool = False
    destructive: bool = False
    operations: list[ToolOperation] = Field(default_factory=list)


class DirectorPlan(BaseModel):
    """Plan node output (agent-director §22): ordered operations for the executor."""

    objective: str
    steps: list[ToolOperation]
    requires_clarification: bool = False
    clarification_message: str | None = None


class DirectorSelection(BaseModel):
    """Frontend selection context attached to every agent request (contract §78, frontend-ux §44)."""

    workspace: str | None = None
    project_id: str | None = None
    episode_id: str | None = None
    scene_id: str | None = None
    shot_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class AgentRunCreate(BaseModel):
    project_id: str
    message: str = Field(min_length=1)
    selection: DirectorSelection = Field(default_factory=DirectorSelection)


class AgentRunRead(BaseModel):
    id: str
    project_id: str
    status: str  # created|running|waiting_approval|waiting_human|completed|failed|cancelled (contract + P7)
    current_stage: str | None
    plan: DirectorPlan | None = None
    approval: dict | None = None
    change_set_id: str | None = None
    result: dict | None = None
    # P7-T012: pending proposal summaries surfaced when the run is WAITING_HUMAN.
    pending_proposals: list[dict] = Field(default_factory=list)
    # 自主迭代 05（刷新恢复）：会话消息转录 [{role, content}]，从 input+result+status
    # 确定性计算——刷新/重开后前端据此水合对话流。
    messages: list[dict] = Field(default_factory=list)
    created_at: str
    updated_at: str


class RiskAssessment(BaseModel):
    """Structured risk classification of one planned tool operation (agent-director
    §24, P2-E3-T02). reason/scope/cost are surfaced to the human reviewer — never
    free-form prose from the LLM."""

    risk_level: Literal["R0", "R1", "R2", "R3"]
    reason: str
    affected_entities: list[str] = Field(default_factory=list)
    estimated_tasks: int | None = None
    estimated_cost: float | None = None
    irreversible: bool = False


class AgentProposalRead(BaseModel):
    """A structured, human-reviewable change proposed by the agent (P7-T012)."""

    id: str
    run_id: str
    tool: str
    target_type: str  # shot
    target_id: str
    base_revision: int
    changes: dict = Field(default_factory=dict)
    status: str
    conflict_reason: str | None = None
    error_message: str | None = None
    created_at: str
    decided_at: str | None = None
    # P2-E3-T02: risk metadata shown on the approval card (affected entities,
    # task/cost estimate, irreversibility) + expiry semantics.
    risk_level: str | None = None
    reason: str | None = None
    estimated_tasks: int | None = None
    estimated_cost: float | None = None
    irreversible: bool = False
    expires_at: str | None = None


class ChangeSetRead(BaseModel):
    """One undoable Agent mutation (P2-E3-T03): minimal before/after patch."""

    id: str
    project_id: str
    run_id: str | None = None
    source: str  # agent | undo
    tool: str
    entity_type: str  # shot
    entity_id: str
    revision_before: int
    revision_after: int
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    undone: bool = False
    undone_at: str | None = None
    undone_by_change_set_id: str | None = None
    created_at: str


class UndoRequest(BaseModel):
    """Body for POST /agent/change-sets/{id}/undo.

    force=True applies the recorded before-values even when a later edit changed
    the same fields (the 409 recovery path); default False conflicts instead.
    """

    force: bool = False


class UndoBatchRequest(BaseModel):
    """Body for POST /agent/runs/{run_id}/change-sets/undo (per-item results)."""

    force: bool = False


class ProposalResumeRequest(BaseModel):
    """Body for POST /agent/runs/{run_id}/resume (P7-T017/T018), backwards compatible."""

    decision: Literal["approve", "reject"] = "approve"
    proposal_ids: list[str] | None = Field(default=None)


class ContextType(BaseModel):
    """Structured LLM input validated before it reaches the provider (P7-T005/6/7)."""

    context_type: Literal["story_planning", "shot_planning", "prompt"]
    project_id: str
    shot_id: str | None = None
    scene_id: str | None = None
