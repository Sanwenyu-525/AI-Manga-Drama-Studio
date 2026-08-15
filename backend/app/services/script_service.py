"""ScriptService (backend-architecture §12, mvp-spec §58): AI analysis of novel/screenplay text.

- analyze_episode: source_text → LLM ScenePlan[] → persist scenes (after user preview/confirm)
- generate_shot_plans: scene → LLM ShotPlan[] → persist shots via ShotService

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

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import Episode, Scene
from app.domain.analysis import AnalysisResult, ScenePlan, ShotPlan, ShotPlanResult
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
)

# Idempotency keys hash the EXACT input sent to the LLM (not the LLM output —
# real models are non-deterministic). Keys are hex prefixes stored on the rows.
_ANALYSIS_SOURCE_CAP = 6000  # hard cap for context budget (must match the prompt)
_KEY_LENGTH = 16


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

        plans = await self._request_scene_plans(episode)
        try:
            self._replace_ai_scenes(episode_id)
            scenes = self.scene_service.create_scenes(
                episode_id,
                [scene_plan_to_create(p) for p in plans],
                analysis_key=key,
            )
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

    async def preview_analysis(self, episode_id: str) -> list[ScenePlan]:
        """LLM analysis WITHOUT persisting — for the Review-before-commit UX (mvp-spec §60)."""
        episode = self._require_episode_with_source(episode_id)
        return await self._request_scene_plans(episode)

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

    async def _request_scene_plans(self, episode: Episode) -> list[ScenePlan]:
        source = (episode.source_text or "")[:_ANALYSIS_SOURCE_CAP]
        prompt = (
            f"剧集标题：{episode.title or episode.episode_number}\n"
            f"小说/剧本原文：\n{source}\n\n"
            "请输出场景列表。"
        )
        return await self.llm.structured_list(ScenePlan, ANALYZE_SYSTEM_PROMPT, prompt)  # type: ignore[return-value]

    @staticmethod
    def _episode_analysis_key(episode: Episode) -> str:
        """Hash of the exact LLM input for episode analysis (truncated source text)."""
        source = (episode.source_text or "")[:_ANALYSIS_SOURCE_CAP]
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:_KEY_LENGTH]

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
            shots = self.shot_service.create_shots(
                scene_id,
                [shot_plan_to_create(p) for p in plans],
                analysis_key=key,
            )
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
