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


class ToolOperation(BaseModel):
    """One deterministic tool call planned by the LLM (agent-director §28-31)."""

    tool: Literal["get_shot", "update_shot", "generate_image", "get_scene_shots"]
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
    created_at: str
    updated_at: str


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
