"""ScriptService (backend-architecture §12, mvp-spec §58): AI analysis of novel/screenplay text.

- analyze_episode: source_text → LLM ScenePlan[] → persist scenes (after user preview/confirm)
- generate_shot_plans: scene → LLM ShotPlan[] → persist shots via ShotService

Depends on the LLMGateway protocol only — never on a concrete model (red line).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import Episode, Scene
from app.domain.analysis import AnalysisResult, ScenePlan, ShotPlan, ShotPlanResult
from app.domain.scene import SceneCreate
from app.llm.gateway import LLMGateway
from app.repositories import EpisodeRepository, SceneRepository
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
        """Run LLM scene planning over the episode's source_text and persist scenes."""
        episode = self._require_episode_with_source(episode_id)

        plans = await self._request_scene_plans(episode)
        created_ids = [self.scene_service.create_scene(episode_id, SceneCreate(**plan.model_dump())).id for plan in plans]
        logger.info("episode %s analyzed: %d scenes", episode_id, len(created_ids))
        return AnalysisResult(episode_id=episode_id, scene_plans=plans, created_scene_ids=created_ids)

    async def preview_analysis(self, episode_id: str) -> list[ScenePlan]:
        """LLM analysis WITHOUT persisting — for the Review-before-commit UX (mvp-spec §60)."""
        episode = self._require_episode_with_source(episode_id)
        return await self._request_scene_plans(episode)

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
        source = episode.source_text[:6000]  # hard cap for context budget
        prompt = (
            f"剧集标题：{episode.title or episode.episode_number}\n"
            f"小说/剧本原文：\n{source}\n\n"
            "请输出场景列表。"
        )
        return await self.llm.structured_list(ScenePlan, ANALYZE_SYSTEM_PROMPT, prompt)  # type: ignore[return-value]

    # --- shot planning ---

    async def generate_shot_plans(self, scene_id: str) -> ShotPlanResult:
        """LLM storyboard planning for a scene, persisted via ShotService."""
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise NotFoundError("Scene does not exist.", {"scene_id": scene_id})
        episode = self.session.get(Episode, scene.episode_id)

        scene_context = (
            f"场景：{scene.name or '未命名'}\n"
            f"地点：{scene.location_id or '未指定'}\n"
            f"时间：{scene.time_of_day or '未指定'}\n"
            f"情绪：{scene.mood or '未指定'}\n"
            f"描述：{scene.description or '无'}\n"
        )
        source_hint = f"\n所属剧集原文摘录：\n{(episode.source_text or '')[:2000]}" if episode else ""
        prompt = scene_context + source_hint + "\n请输出该场景的分镜镜头列表。"

        plans = await self.llm.structured_list(ShotPlan, SHOT_PLAN_SYSTEM_PROMPT, prompt)  # type: ignore[return-value]
        created_ids = [
            self.shot_service.create_shot(scene_id, self._shot_create(plan)).id for plan in plans
        ]
        logger.info("scene %s storyboard planned: %d shots", scene_id, len(created_ids))
        return ShotPlanResult(scene_id=scene_id, shot_plans=plans, created_shot_ids=created_ids)

    @staticmethod
    def _shot_create(plan: ShotPlan):
        from app.domain.shot import ShotCreate

        return ShotCreate(
            shot_type=plan.shot_type,
            camera_angle=plan.camera_angle,
            camera_movement=plan.camera_movement,
            duration=plan.duration,
            action=plan.action,
            emotion=plan.emotion,
            dialogue=plan.dialogue,
            image_prompt=plan.image_prompt,
        )
