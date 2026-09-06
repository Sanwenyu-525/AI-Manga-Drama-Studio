"""AnalysisSnapshot model (P2-E1-T01).

Preview 落库的不可变分析快照：confirm 只提交该 snapshot，不重新调用 LLM。
存储 source_hash（送入 LLM 的截断原文 hash）+ episode_revision（预览时点），
confirm 前校验两者——原文或剧集被编辑过 → snapshot 过期（409），要求重新预览。
"""

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, uuid_pk

# Snapshot 生命周期：pending（已预览待确认）→ confirmed（已写入 Project State）；
# expired（confirm 时原文/revision 已变，或被后续 preview 取代——校验失败即标过期）。
SNAPSHOT_STATUSES = ("pending", "confirmed", "expired")

# provenance 版本标签（prompt/schema 变更时 bump，保证快照可追溯）。
# v2 (P2-E1-T02): chunked analysis (no silent truncation) + character candidates.
ANALYSIS_PROMPT_VERSION = "v2"
ANALYSIS_SCHEMA_VERSION = "scene_plan_v1"


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"
    __table_args__ = (
        Index("ix_analysis_snapshots_episode_status", "episode_id", "status"),
    )

    id: Mapped[str] = uuid_pk()
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("episodes.id"), nullable=False, index=True
    )
    # 预览时点的输入指纹：source_hash = 送入 LLM 的截断原文 hash（同 analysis_key 语义）
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    episode_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # 用户审阅的确切计划（ScenePlan[] JSON）——confirm 写入的唯一事实源。
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    # provenance：模型名 / prompt 版本 / schema 版本（AC: 可追溯）。
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False, default=ANALYSIS_PROMPT_VERSION)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False, default=ANALYSIS_SCHEMA_VERSION)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # P2-E1-T02: LLM-extracted character candidates (JSON) — immutable like plans,
    # so refresh rehydration and the decisions endpoint share one server truth.
    character_candidates_json: Mapped[str | None] = mapped_column(Text)
    created_scene_ids_json: Mapped[str | None] = mapped_column(Text)  # confirm 结果（幂等重放）
    created_at: Mapped[str] = ts_created()
    confirmed_at: Mapped[str | None] = mapped_column(Text)
