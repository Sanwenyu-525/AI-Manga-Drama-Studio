"""AgentRun / AgentProposal / AgentChangeSet models (P7 + P2-E3-T02/T03).

P7-T001: agent_runs is the durable source of truth for AI Director runs —
LangGraph Checkpointer (thread_id = run_id) stores the graph execution state,
while this table stores the business-level run record (status, inputs, plan).
Created from the in-memory AgentRunStore (Stage D) for crash-safe resume.

P7-T012/T013: agent_proposals capture a structured, human-reviewable change
requested by the agent (e.g. an update_shot edit). They are NEVER applied to the
domain directly — a ProposalService applies them through ShotService after human
approval, guarded by a base_revision optimistic-concurrency check (P7-T016).

P2-E3-T02: proposals carry structured risk metadata (R0–R3 classification,
estimated tasks/cost, irreversibility) and expire after a TTL.
P2-E3-T03: agent_change_sets record every applied Agent mutation as a minimal
before/after patch so it can be reviewed and undone (compensating change).
"""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

# Run-level state machine (api-event-contract §26 + P7-T017 WAITING_HUMAN).
# P8-T018: continuity_check runs the Continuity Agent semantic check;
# P8-T019: continuity_fix runs a fix proposal for a specific warning.
RUN_RUN_TYPES = ("director", "continuity_check", "continuity_fix")
RUN_STATUSES = (
    "created",
    "running",
    "waiting_approval",  # back-compat alias surfaced by the in-memory MVP
    "waiting_human",  # P7-T017: run suspended awaiting human approval
    "completed",
    "failed",
    "cancelled",
    "cancelling",
)

# Proposal lifecycle (design ai-director-agent §42-43, P7-T012).
PROPOSAL_STATUSES = (
    "pending",  # created, awaiting human review
    "approved",  # human approved; not yet applied
    "rejected",  # human rejected; never applied
    "conflict",  # base_revision mismatch at apply time; not applied
    "applied",  # successfully applied via ShotService
    "expired",  # P2-E3-T02: TTL elapsed before a decision; never applied
)

# ChangeSet sources (P2-E3-T03; P4-E3-T02 adds "timeline" for user Timeline edits).
CHANGE_SET_SOURCES = ("agent", "undo", "timeline")

# Structured shot field changes allowed in an update_shot-style proposal.
SHOT_CHANGE_FIELDS = (
    "shot_type",
    "camera_angle",
    "camera_movement",
    "lens",
    "duration",
    "action",
    "emotion",
    "dialogue",
    "image_prompt",
    "negative_prompt",
    "status",
    "dirty_state",
)


class AgentRun(Base):
    """Business record of one AI Director run (api-event-contract §23-31)."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(Text, nullable=False, default="director")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    current_stage: Mapped[str | None] = mapped_column(Text)

    input_json: Mapped[str | None] = mapped_column(Text)  # {message, selection, ...} (AgentRunCreate)
    messages_json: Mapped[str | None] = mapped_column(Text)  # agent message transcript (interface trace)
    plan_json: Mapped[str | None] = mapped_column(Text)  # parsed DirectorPlan (plan.created)
    result_json: Mapped[str | None] = mapped_column(Text)  # final_result (run.completed)

    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class AgentProposal(Base):
    """A structured, human-reviewable change the agent proposes (P7-T012).

    Stored pending on creation; the run moves to WAITING_HUMAN. A human approves /
    rejects it; on approve the ProposalService applies the change through ShotService
    AFTER validating base_revision matches the shot's current revision (P7-T016).
    """

    __tablename__ = "agent_proposals"
    __table_args__ = (
        Index("ix_agent_proposals_run_status", "run_id", "status"),
        Index("ix_agent_proposals_target", "target_type", "target_id"),
    )

    id: Mapped[str] = uuid_pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    tool: Mapped[str] = mapped_column(Text, nullable=False)  # update_shot | generate_image | continuity_fix
    target_type: Mapped[str] = mapped_column(Text, nullable=False)  # shot
    target_id: Mapped[str] = mapped_column(Text, nullable=False)  # shot id
    base_revision: Mapped[int] = mapped_column(nullable=False)  # shot revision at proposal time
    changes_json: Mapped[str | None] = mapped_column(Text)  # structured field changes {field: value}
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    conflict_reason: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    # P2-E3-T02: structured risk metadata + expiry.
    risk_level: Mapped[str | None] = mapped_column(Text)  # R0..R3
    reason: Mapped[str | None] = mapped_column(Text)  # human-readable classification reason
    estimated_tasks: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column()
    irreversible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[str | None] = mapped_column(Text)  # ISO timestamp; past → expired
    created_at: Mapped[str] = ts_created()
    decided_at: Mapped[str | None] = mapped_column(Text)


class AgentChangeSet(Base):
    """One applied Agent mutation, recorded as a minimal before/after patch
    (P2-E3-T03). Undo NEVER edits history — it applies the before-values as a
    NEW compensating change (a new AgentChangeSet with source="undo") and links
    back to the original via undone_by_change_set_id."""

    __tablename__ = "agent_change_sets"
    __table_args__ = (
        Index("ix_agent_change_sets_project", "project_id"),
        Index("ix_agent_change_sets_run", "run_id"),
        Index("ix_agent_change_sets_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    source: Mapped[str] = mapped_column(Text, nullable=False, default="agent")  # agent | undo
    tool: Mapped[str] = mapped_column(Text, nullable=False)  # update_shot | generate_image | undo_shot_patch ...
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)  # shot
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)  # shot id

    revision_before: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_after: Mapped[int] = mapped_column(Integer, nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text)  # {field: value} before the mutation
    after_json: Mapped[str | None] = mapped_column(Text)  # {field: value} after the mutation

    undone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    undone_at: Mapped[str | None] = mapped_column(Text)
    undone_by_change_set_id: Mapped[str | None] = mapped_column(Text)  # compensating change_set id

    created_at: Mapped[str] = ts_created()
