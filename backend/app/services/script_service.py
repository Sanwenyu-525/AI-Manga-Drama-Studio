"""ScriptService (backend-architecture §12, mvp-spec §58): AI analysis of novel/screenplay text.

- analyze_episode: source_text → LLM ScenePlan[] → persist scenes (after user preview/confirm)
- generate_shot_plans: scene → LLM ShotPlan[] → persist shots via ShotService

P2-E1-T01 (Analysis Snapshot):

- preview_analysis persists an IMMUTABLE AnalysisSnapshot (plans + source_hash +
  episode_revision + provenance). Confirm submits the snapshot_id and writes
  EXACTLY the reviewed plans — no second LLM call, so real-model nondeterminism
  can never make the persisted content differ from what the user previewed
  (Sprint 04 evidence: two independent LLM calls per preview/confirm pair).
- Confirm is idempotent (a confirmed snapshot replays its created_scene_ids)
  and expires (409) when the source text or episode revision changed after
  preview — the user must re-preview.

P1-E1-T01 (修复 AI 计划映射与批量写入事务):

- Plans are mapped to domain creates through ONE explicit mapper
  (app.services.plan_mapper) — no field is silently dropped.
- Each confirm flow runs inside ONE transaction: all-or-nothing; any failure
  rolls back and leaves no partial Scenes/Shots.
- Re-submitting the SAME request is idempotent (analysis_key / storyboard_key):
  same input → no-op returning the already-persisted rows.
- Re-submitting with DIFFERENT input replaces the previous AI-created rows
  (soft delete + recreate); manually created rows (analysis_key IS NULL) are
  preserved. Legacy rows without keys are treated as manual (P1-E1-T02 owns
  legacy duplicate detection).
- Events are published AFTER the single commit (red line: commit then publish).

Depends on the LLMGateway protocol only — never on a concrete model (red line).
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import AnalysisSnapshot, Episode, Scene
from app.db.models.analysis import ANALYSIS_PROMPT_VERSION, ANALYSIS_SCHEMA_VERSION
from app.domain.analysis import (
    AnalysisPreview,
    AnalysisResult,
    CharacterCandidate,
    CharacterCandidateRead,
    CharacterDecisionResult,
    CharacterDecisionsRequest,
    CharacterDecisionsResult,
    ScenePlan,
    ShotPlan,
    ShotPlanResult,
    SnapshotRead,
)
from app.events.bus import EVENT_SCENE_CREATED, EVENT_SHOT_CREATED, StudioEvent, bus
from app.llm.gateway import LLMGateway
from app.repositories import EpisodeRepository, SceneRepository
from app.services.plan_mapper import (
    scene_plan_to_create,
    scene_to_plan,
    shot_plan_to_create,
    shot_to_plan,
)
from app.services.scene_service import SceneService
from app.services.shot_service import ShotService

logger = get_logger("script")

ANALYZE_SYSTEM_PROMPT = (
    "你是漫剧制作 Studio 的剧本分析引擎。把小说/剧本文本拆分为结构化的场景列表。"
    "每个场景包含：场景编号、标题、地点、时间、描述、情绪基调。"
    "严格遵守输出的 JSON 结构，不要输出任何额外文字。"
)

SHOT_PLAN_SYSTEM_PROMPT = (
    "你是漫剧分镜师。根据场景信息生成分镜镜头列表。"
    "每个镜头包含：镜头编号、景别（extreme_wide/wide/full/medium/close_up/extreme_close_up）、"
    "机位角度、镜头运动、时长（秒）、动作、情绪、对白、图片生成提示词。"
    "镜头之间保持动作与空间连续性。严格遵守输出的 JSON 结构，不要输出任何额外文字。"
    "图片生成提示词（image_prompt）必须使用英文——中文描述会导致图片模型生成效果不稳定（TASK-008 实测结论）。"
)

# Idempotency keys hash the EXACT input sent to the LLM (not the LLM output —
# real models are non-deterministic). Keys are hex prefixes stored on the rows.
_ANALYSIS_CHUNK_CHARS = 6000  # one LLM call covers at most this many source chars
_ANALYSIS_MAX_CHUNKS = 4  # ... and at most this many chunks per preview
_ANALYSIS_MAX_CHARS = _ANALYSIS_CHUNK_CHARS * _ANALYSIS_MAX_CHUNKS  # 24000
_KEY_LENGTH = 16

# Setting-document digest budget (mvp-spec DOC-004): injected BEFORE the source
# text and included in the idempotency key, so a changed setting re-analyzes.
_DOCUMENT_DIGEST_CAP = 2000


class ScriptService:
    def __init__(self, session: Session, llm: LLMGateway) -> None:
        self.session = session
        self.llm = llm
        self.episodes = EpisodeRepository(session)
        self.scenes = SceneRepository(session)
        self.scene_service = SceneService(session)
        self.shot_service = ShotService(session)

    # --- analysis ---

    async def analyze_episode(self, episode_id: str) -> AnalysisResult:
        """Run LLM scene planning over the episode's source_text and persist scenes.

        Idempotent: the same source (same analysis key) with live scenes returns
        the persisted scenes without calling the LLM. A different source replaces
        the previous AI-created scenes; manual scenes are preserved.
        """
        episode = self._require_episode_with_source(episode_id)
        self._check_source_length(episode)
        key = self._episode_analysis_key(episode)

        existing = self.scenes.list_all(episode_id=episode_id, analysis_key=key)
        if episode.analysis_key == key and existing:
            logger.info(
                "episode %s analysis idempotent (key=%s): reusing %d scenes",
                episode_id, key, len(existing),
            )
            return AnalysisResult(
                episode_id=episode_id,
                scene_plans=[scene_to_plan(s) for s in existing],
                created_scene_ids=[s.id for s in existing],
            )

        plans, _chunk_count = await self._request_scene_plans(episode)
        try:
            self._replace_ai_scenes(episode_id)
            # LLM 的 scene_number 只是顺序提示：flush 软删后按「live 场景之后」统一
            # 重编号。否则被保留的场景（手动 analysis_key=NULL，或早期未打标的
            # legacy 数据）已占用 LLM 输出的编号时，会撞 (episode_id, scene_number)
            # 唯一索引 → IntegrityError。纯 AI 重分析时软删已释放 1..N，编号不变。
            self.session.flush()
            next_number = self.scenes.next_scene_number(episode_id)
            creates = []
            for offset, plan in enumerate(plans):
                data = scene_plan_to_create(plan)
                data.scene_number = next_number + offset
                creates.append(data)
            scenes = self.scene_service.create_scenes(episode_id, creates, analysis_key=key)
            episode.analysis_key = key
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        for scene in scenes:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_SCENE_CREATED,
                    entity_type="scene",
                    entity_id=scene.id,
                    project_id=episode.project_id,
                )
            )
        logger.info("episode %s analyzed (key=%s): %d scenes", episode_id, key, len(scenes))
        return AnalysisResult(
            episode_id=episode_id,
            scene_plans=plans,
            created_scene_ids=[s.id for s in scenes],
        )

    async def preview_analysis(self, episode_id: str) -> AnalysisPreview:
        """P2-E1-T01: LLM analysis persisted as an IMMUTABLE snapshot.

        The plans the user reviews are exactly the plans a later confirm writes
        (confirm reads the snapshot; it never calls the LLM again). Also lets the
        frontend rehydrate the preview after a refresh (AC: 刷新后可读取状态).

        P2-E1-T02: long texts are analyzed in sequential chunks (no silent
        truncation); a chunk failure aborts BEFORE anything is persisted, so a
        retry re-runs the same chunking and lands a consistent snapshot.
        Character candidates are extracted in one extra call and stored on the
        snapshot — the decisions endpoint later reads them as server truth.
        """
        episode = self._require_episode_with_source(episode_id)
        self._check_source_length(episode)
        plans, chunk_count = await self._request_scene_plans(episode)
        candidates = await self._request_character_candidates(episode)
        candidate_reads = self._match_candidates(episode.project_id, candidates)
        snapshot = AnalysisSnapshot(
            episode_id=episode_id,
            source_hash=self._episode_analysis_key(episode),
            episode_revision=episode.revision,
            plan_json=json.dumps(
                [p.model_dump() for p in plans], ensure_ascii=False
            ),
            character_candidates_json=json.dumps(
                [c.model_dump() for c in candidates], ensure_ascii=False
            ),
            model=self._script_model_provenance(),
            prompt_version=ANALYSIS_PROMPT_VERSION,
            schema_version=ANALYSIS_SCHEMA_VERSION,
            status="pending",
        )
        self.session.add(snapshot)
        self.session.commit()
        source_chars = len(episode.source_text or "")
        logger.info(
            "episode %s preview snapshot %s persisted (%d plans, %d chunks, %d candidates, model=%s)",
            episode_id, snapshot.id, len(plans), chunk_count, len(candidates), snapshot.model,
        )
        return AnalysisPreview(
            snapshot_id=snapshot.id,
            episode_id=episode_id,
            source_hash=snapshot.source_hash,
            plans=plans,
            model=snapshot.model,
            source_chars=source_chars,
            analyzed_chars=min(source_chars, _ANALYSIS_MAX_CHARS),
            chunk_count=chunk_count,
            llm_calls=chunk_count + 1,
            max_chars=_ANALYSIS_MAX_CHARS,
            character_candidates=candidate_reads,
        )

    async def confirm_snapshot(self, episode_id: str, snapshot_id: str) -> AnalysisResult:
        """P2-E1-T01: write the reviewed snapshot plans — ZERO LLM calls.

        - Idempotent: a confirmed snapshot replays its created_scene_ids.
        - Expired (409): source text or episode revision changed since preview
          (the LLM input would differ from what the user reviewed).
        - Write semantics identical to analyze_episode (replace AI scenes,
          preserve manual ones, all-or-nothing, commit then publish).
        """
        snapshot = self.session.get(AnalysisSnapshot, snapshot_id)
        if snapshot is None:
            raise NotFoundError("Analysis snapshot does not exist.", {"snapshot_id": snapshot_id})
        if snapshot.episode_id != episode_id:
            raise ValidationError(
                "Snapshot belongs to a different episode.",
                {"snapshot_id": snapshot_id, "episode_id": episode_id},
            )

        plans = [ScenePlan.model_validate(p) for p in json.loads(snapshot.plan_json)]

        if snapshot.status == "confirmed":
            logger.info("snapshot %s confirm idempotent: replaying scene ids", snapshot_id)
            return AnalysisResult(
                episode_id=episode_id,
                scene_plans=plans,
                created_scene_ids=json.loads(snapshot.created_scene_ids_json or "[]"),
            )
        if snapshot.status == "expired":
            raise ConflictError(
                "Analysis snapshot has expired. Re-run the preview.",
                {"snapshot_id": snapshot_id, "reason": "expired"},
            )

        episode = self._require_episode_with_source(episode_id)
        current_hash = self._episode_analysis_key(episode)
        if current_hash != snapshot.source_hash or episode.revision != snapshot.episode_revision:
            snapshot.status = "expired"
            self.session.commit()
            raise ConflictError(
                "Episode changed after the preview. Re-run the preview.",
                {
                    "snapshot_id": snapshot_id,
                    "reason": "source_changed" if current_hash != snapshot.source_hash else "revision_changed",
                    "preview_revision": snapshot.episode_revision,
                    "current_revision": episode.revision,
                },
            )

        # --- persist exactly the reviewed plans (same write path as analyze_episode)
        try:
            self._replace_ai_scenes(episode_id)
            # flush 软删后统一重编号（同 analyze_episode：避免撞唯一索引）。
            self.session.flush()
            next_number = self.scenes.next_scene_number(episode_id)
            creates = []
            for offset, plan in enumerate(plans):
                data = scene_plan_to_create(plan)
                data.scene_number = next_number + offset
                creates.append(data)
            scenes = self.scene_service.create_scenes(
                episode_id, creates, analysis_key=snapshot.source_hash
            )
            # flush 让 Python 侧 uuid 主键生效（json.dumps 在 commit 前需要真实 id）。
            self.session.flush()
            episode.analysis_key = snapshot.source_hash
            snapshot.status = "confirmed"
            snapshot.created_scene_ids_json = json.dumps([s.id for s in scenes])
            from app.db.models.columns import utcnow_iso

            snapshot.confirmed_at = utcnow_iso()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        for scene in scenes:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_SCENE_CREATED,
                    entity_type="scene",
                    entity_id=scene.id,
                    project_id=episode.project_id,
                )
            )
        logger.info(
            "episode %s confirmed from snapshot %s: %d scenes (no LLM call)",
            episode_id, snapshot_id, len(scenes),
        )
        return AnalysisResult(
            episode_id=episode_id,
            scene_plans=plans,
            created_scene_ids=[s.id for s in scenes],
        )

    def get_latest_snapshot(self, episode_id: str) -> SnapshotRead | None:
        """Newest snapshot for an episode (refresh rehydration / audit)."""
        stmt = (
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.episode_id == episode_id)
            .order_by(AnalysisSnapshot.created_at.desc())
            .limit(20)
        )
        rows = list(self.session.scalars(stmt))
        if not rows:
            return None
        snap = rows[0]
        episode = self.episodes.get(episode_id)
        scope = self._snapshot_scope(episode) if episode is not None else {
            "source_chars": 0, "analyzed_chars": 0,
            "chunk_count": 1, "llm_calls": 2, "max_chars": _ANALYSIS_MAX_CHARS,
        }
        candidates = self._load_snapshot_candidates(snap)
        candidate_reads = (
            self._match_candidates(episode.project_id, candidates)
            if episode is not None else
            [CharacterCandidateRead(name=c.name, description=c.description) for c in candidates]
        )
        return SnapshotRead(
            id=snap.id,
            episode_id=snap.episode_id,
            source_hash=snap.source_hash,
            episode_revision=snap.episode_revision,
            status=snap.status,
            plans=[ScenePlan.model_validate(p) for p in json.loads(snap.plan_json)],
            model=snap.model,
            prompt_version=snap.prompt_version,
            schema_version=snap.schema_version,
            created_scene_ids=json.loads(snap.created_scene_ids_json or "[]"),
            created_at=snap.created_at,
            character_candidates=candidate_reads,
            **scope,
        )

    @staticmethod
    def _script_model_provenance() -> str | None:
        """Best-effort model name for the script task (never breaks preview)."""
        try:
            from app.services.llm_settings_service import get_task_llm_config

            return get_task_llm_config("script").get("model")
        except Exception:  # noqa: BLE001 — provenance is advisory
            return None

    def _replace_ai_scenes(self, episode_id: str) -> None:
        """Soft-delete previous AI-created scenes (analysis_key IS NOT NULL) and their
        shots. Manual scenes (analysis_key IS NULL) are preserved. No commit."""
        ai_scenes = [s for s in self.scenes.list_all(episode_id=episode_id) if s.analysis_key is not None]
        if not ai_scenes:
            return
        self.shot_service.soft_delete_shots([s.id for s in ai_scenes])
        self.scene_service.soft_delete_scenes([s.id for s in ai_scenes])

    def _require_episode_with_source(self, episode_id: str) -> Episode:
        from app.core.errors import ValidationError

        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        if not episode.source_text or not episode.source_text.strip():
            raise ValidationError(
                "Episode has no source_text. Import novel text before analysis.",
                {"episode_id": episode_id},
            )
        return episode

    def _check_source_length(self, episode: Episode) -> None:
        """P2-E1-T02: refuse over-limit texts with an actionable message instead
        of silently truncating (AC: 不静默截断)."""
        chars = len(episode.source_text or "")
        if chars > _ANALYSIS_MAX_CHARS:
            raise ValidationError(
                f"原文共 {chars} 字，超过单次分析上限 {_ANALYSIS_MAX_CHARS} 字"
                f"（{_ANALYSIS_MAX_CHUNKS} 块 × {_ANALYSIS_CHUNK_CHARS} 字）。"
                "请拆分成多集后分别导入分析。",
                {"source_chars": chars, "max_chars": _ANALYSIS_MAX_CHARS},
            )

    @staticmethod
    def _split_source(source: str) -> list[str]:
        """Split into ≤_ANALYSIS_CHUNK_CHARS chunks on paragraph boundaries.

        Deterministic: the same source always yields the same chunks, so a
        retried preview lands a consistent snapshot (AC: 分块失败可重试).
        """
        paras = [p for p in source.split("\n") if p.strip()]
        if not paras:
            return [source] if source else []
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for para in paras:
            # A single giant paragraph is hard-split (no silent drop).
            while len(para) > _ANALYSIS_CHUNK_CHARS:
                if current:
                    chunks.append("\n".join(current))
                    current, current_len = [], 0
                chunks.append(para[:_ANALYSIS_CHUNK_CHARS])
                para = para[_ANALYSIS_CHUNK_CHARS:]
            if current_len + len(para) + 1 > _ANALYSIS_CHUNK_CHARS and current:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            current.append(para)
            current_len += len(para) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks or [source]

    def _analysis_digest(self, project_id: str) -> str:
        """Setting-document digest shared by every chunk prompt and the key."""
        from app.services.document_service import DocumentService

        digest = DocumentService(self.session).render_digest(
            project_id, max_chars=_DOCUMENT_DIGEST_CAP
        )
        return f"设定文档（项目归档，仅供参考）：\n{digest}\n\n" if digest else ""

    def _analysis_chunks(self, episode: Episode) -> tuple[str, list[str]]:
        """Digest head + source chunks (each ≤ _ANALYSIS_CHUNK_CHARS)."""
        source = episode.source_text or ""
        return self._analysis_digest(episode.project_id), self._split_source(source)

    async def _request_scene_plans(self, episode: Episode) -> tuple[list[ScenePlan], int]:
        """Scene planning over sequential chunks; merged + globally renumbered.

        A chunk failure aborts BEFORE anything is persisted (callers only write
        the snapshot/rows after this returns), so retrying the preview re-runs
        the same deterministic chunking and lands a consistent snapshot.
        """
        digest, chunks = self._analysis_chunks(episode)
        title = f"剧集标题：{episode.title or episode.episode_number}\n"
        merged: list[ScenePlan] = []
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            scope = f"原文第 {index}/{total} 部分（本块 {len(chunk)} 字）：\n" if total > 1 else ""
            prompt = f"{title}{digest}小说/剧本{scope}\n{chunk}\n\n请输出场景列表。"
            try:
                plans = await self.llm.structured_list(ScenePlan, ANALYZE_SYSTEM_PROMPT, prompt)  # type: ignore[assignment]
            except Exception as exc:
                raise RuntimeError(
                    f"第 {index}/{total} 部分场景分析失败，重试本次预览即可（未写入任何内容）。"
                ) from exc
            for plan in plans:
                plan.scene_number = len(merged) + 1
                merged.append(plan)
        logger.info(
            "episode %s scene planning: %d chunks → %d scenes",
            episode.id, total, len(merged),
        )
        return merged, total

    CHARACTER_EXTRACT_SYSTEM_PROMPT = (
        "你是漫剧制作 Studio 的角色提取器。从小说/剧本原文中识别有实质出场的人物。"
        "只输出真实出现的人物，不要虚构；每个人物一句话描述其身份/外貌/性格。"
        "严格遵守输出的 JSON 结构，不要输出任何额外文字。"
    )

    async def _request_character_candidates(self, episode: Episode) -> list[CharacterCandidate]:
        """One extraction call over the analyzed source (never auto-created)."""
        digest, chunks = self._analysis_chunks(episode)
        prompt = (
            f"剧集标题：{episode.title or episode.episode_number}\n"
            f"{digest}小说/剧本原文：\n{"\n---\n".join(chunks)}\n\n"
            "请输出人物候选列表。"
        )
        try:
            return await self.llm.structured_list(CharacterCandidate, self.CHARACTER_EXTRACT_SYSTEM_PROMPT, prompt)  # type: ignore[return-value]
        except Exception as exc:
            raise RuntimeError("人物候选提取失败，重试本次预览即可（未写入任何内容）。") from exc

    def _match_candidates(
        self, project_id: str, candidates: list[CharacterCandidate]
    ) -> list[CharacterCandidateRead]:
        """Attach same-project exact-name matches as merge suggestions."""
        from app.services.character_service import CharacterService

        existing = {c.name: c for c in CharacterService(self.session).list_characters(project_id)}
        return [
            CharacterCandidateRead(
                name=c.name,
                description=c.description,
                existing_character_id=existing[c.name].id if c.name in existing else None,
                existing_character_name=c.name if c.name in existing else None,
            )
            for c in candidates
        ]

    def _episode_analysis_key(self, episode: Episode) -> str:
        """Hash of the exact LLM input (digest + FULL source + chunking).

        P2-E1-T02 changed the strategy (v2 prompt): old v1 snapshots hash the
        truncated input, so they expire on next confirm — re-preview required.
        """
        digest = self._analysis_digest(episode.project_id)
        return hashlib.sha256(
            (digest + (episode.source_text or "")).encode("utf-8")
        ).hexdigest()[:_KEY_LENGTH]

    def _snapshot_scope(self, episode: Episode) -> dict[str, int]:
        """Transparency counters shared by preview + latest-snapshot read."""
        source_chars = len(episode.source_text or "")
        chunks = self._split_source(episode.source_text or "")
        chunk_count = len(chunks)
        return {
            "source_chars": source_chars,
            "analyzed_chars": min(source_chars, _ANALYSIS_MAX_CHARS),
            "chunk_count": chunk_count,
            "llm_calls": chunk_count + 1,  # scene chunks + one candidate extraction
            "max_chars": _ANALYSIS_MAX_CHARS,
        }

    def _load_snapshot_candidates(self, snapshot: AnalysisSnapshot) -> list[CharacterCandidate]:
        try:
            return [CharacterCandidate.model_validate(c) for c in json.loads(snapshot.character_candidates_json or "[]")]
        except Exception:  # noqa: BLE001 — legacy v1 snapshots have no candidates
            return []

    async def apply_character_decisions(
        self, episode_id: str, body: CharacterDecisionsRequest
    ) -> CharacterDecisionsResult:
        """P2-E1-T02: create / merge / skip reviewed candidates (per-item results).

        Candidate identity comes from the immutable snapshot (server truth);
        the client only picks the action. Nothing is auto-created: an explicit
        decision per name is required, and duplicate-name creates conflict.
        """
        from app.domain.character import CharacterCreate, CharacterUpdate
        from app.services.character_service import CharacterService

        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Episode does not exist.", {"episode_id": episode_id})
        snapshot = self.session.get(AnalysisSnapshot, body.snapshot_id)
        if snapshot is None or snapshot.episode_id != episode_id:
            raise NotFoundError(
                "Analysis snapshot does not exist for this episode.",
                {"snapshot_id": body.snapshot_id},
            )
        known = {c.name: c for c in self._load_snapshot_candidates(snapshot)}
        characters = CharacterService(self.session)
        live_names = {c.name: c for c in characters.list_characters(episode.project_id)}
        results: list[CharacterDecisionResult] = []
        for decision in body.decisions:
            candidate = known.get(decision.name)
            if candidate is None:
                results.append(CharacterDecisionResult(
                    name=decision.name, action=decision.action,
                    status="failed", message="不在本次预览候选内，请重新预览。",
                ))
                continue
            if decision.action == "skip":
                results.append(CharacterDecisionResult(
                    name=decision.name, action="skip", status="skipped"))
                continue
            if decision.action == "create":
                if decision.name in live_names:
                    results.append(CharacterDecisionResult(
                        name=decision.name, action="create", status="conflict",
                        character_id=live_names[decision.name].id,
                        message=f"已存在同名人物「{decision.name}」，请选择合并或忽略。",
                    ))
                    continue
                created = characters.create_character(
                    episode.project_id,
                    CharacterCreate(name=candidate.name, appearance=candidate.description or None),
                )
                live_names[created.name] = created
                results.append(CharacterDecisionResult(
                    name=decision.name, action="create",
                    status="created", character_id=created.id))
                continue
            # merge: must point at a live same-project character.
            if not decision.character_id:
                results.append(CharacterDecisionResult(
                    name=decision.name, action="merge",
                    status="failed", message="合并需要指定已有人物 character_id。",
                ))
                continue
            try:
                target = characters.get_character(decision.character_id)
            except NotFoundError:
                results.append(CharacterDecisionResult(
                    name=decision.name, action="merge",
                    status="failed", message="指定人物不存在。",
                ))
                continue
            if target.project_id != episode.project_id:
                results.append(CharacterDecisionResult(
                    name=decision.name, action="merge",
                    status="failed", message="指定人物属于其他项目。",
                ))
                continue
            if not target.appearance and candidate.description:
                characters.update_character(
                    target.id, target.revision,
                    CharacterUpdate(appearance=candidate.description),
                )
            results.append(CharacterDecisionResult(
                name=decision.name, action="merge",
                status="merged", character_id=target.id))
        return CharacterDecisionsResult(episode_id=episode_id, results=results)

    # --- shot planning ---

    async def generate_shot_plans(self, scene_id: str) -> ShotPlanResult:
        """LLM storyboard planning for a scene, persisted via ShotService.

        Idempotent: the same scene context (same storyboard key) with live shots
        returns the persisted shots without calling the LLM. A different context
        replaces the previous AI-created shots; manual shots are preserved.
        """
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        episode = self.session.get(Episode, scene.episode_id)

        context = self._storyboard_context(scene, episode)
        key = hashlib.sha256(context.encode("utf-8")).hexdigest()[:_KEY_LENGTH]

        if scene.storyboard_key == key:
            existing = self.shot_service.list_shots_with_key(scene_id, key)
            if existing:
                logger.info(
                    "scene %s shot planning idempotent (key=%s): reusing %d shots",
                    scene_id, key, len(existing),
                )
                return ShotPlanResult(
                    scene_id=scene_id,
                    shot_plans=[shot_to_plan(s) for s in existing],
                    created_shot_ids=[s.id for s in existing],
                )

        plans = await self.llm.structured_list(  # type: ignore[return-value]
            ShotPlan, SHOT_PLAN_SYSTEM_PROMPT, context + "\n请输出该场景的分镜镜头列表。"
        )
        try:
            self.shot_service.soft_delete_ai_shots(scene_id)
            # 同 analyze_episode：flush 软删后按「live 镜头之后」统一重编号，
            # 避免与被保留的手动镜头撞 (scene_id, shot_number) 唯一索引。
            self.session.flush()
            next_number = self.shot_service.next_shot_number(scene_id)
            creates = []
            for offset, plan in enumerate(plans):
                data = shot_plan_to_create(plan)
                data.shot_number = next_number + offset
                creates.append(data)
            shots = self.shot_service.create_shots(scene_id, creates, analysis_key=key)
            scene.storyboard_key = key
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        for shot in shots:
            bus.publish(
                StudioEvent(
                    event_type=EVENT_SHOT_CREATED,
                    entity_type="shot",
                    entity_id=shot.id,
                    project_id=episode.project_id if episode else None,
                )
            )
        logger.info("scene %s storyboard planned (key=%s): %d shots", scene_id, key, len(shots))
        return ShotPlanResult(
            scene_id=scene_id,
            shot_plans=plans,
            created_shot_ids=[s.id for s in shots],
        )

    @staticmethod
    def _storyboard_context(scene: Scene, episode: Episode | None) -> str:
        """Canonical context string — used BOTH for the LLM prompt and the
        idempotency key, so the key always reflects exactly what was analyzed."""
        scene_context = (
            f"场景：{scene.name or '未命名'}\n"
            f"地点：{scene.location_id or '未指定'}\n"
            f"时间：{scene.time_of_day or '未指定'}\n"
            f"情绪：{scene.mood or '未指定'}\n"
            f"描述：{scene.description or '无'}\n"
        )
        source_hint = f"\n所属剧集原文摘录：\n{(episode.source_text or '')[:2000]}" if episode else ""
        return scene_context + source_hint
