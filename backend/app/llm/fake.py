"""FakeLLMGateway — deterministic fake for tests and keyless development (mvp-spec §100, §101).

Returns heuristic but valid ScenePlan / ShotPlan so the whole Stage B chain
(analyze → preview → create scenes → generate shots → storyboard) runs without
any LLM API key. Switch with STUDIO_LLM_MODE=openai for real models.
"""

from __future__ import annotations

import math
from typing import TypeVar

from pydantic import BaseModel

from app.core.logging import get_logger
from app.domain.analysis import ScenePlan, ShotPlan
from app.domain.agent import DirectorPlan, ProductionIntent
from app.agents.fake_planner import parse_director_plan, parse_production_intent

logger = get_logger("llm.fake")

T = TypeVar("T", bound=BaseModel)

# Selection context injected by the graph for fake planning (message → target resolution)
_FAKE_SELECTION: dict = {"shot_id": None}


def set_fake_selection(shot_id: str | None) -> None:
    _FAKE_SELECTION["shot_id"] = shot_id

_MOODS = ["tense", "calm", "warm", "melancholic", "excited"]
_SHOT_TYPES = ["wide", "medium", "close_up", "extreme_close_up", "full", "medium"]
_CAMERA_ANGLES = ["eye_level", "low_angle", "high_angle", "eye_level", "eye_level", "low_angle"]
_MOVEMENTS = ["static", "static", "dolly", "pan", "handheld", "static"]
_ACTIONS = ["人物入场", "对话", "关键动作", "反应", "环境空镜", "情绪特写"]


class FakeLLMGateway:
    """Deterministic implementation of the LLMGateway protocol."""

    async def invoke(self, system: str, prompt: str) -> str:
        logger.info("fake invoke (len=%d)", len(prompt))
        return f"FAKE: {prompt[:120]}…"

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        if schema is ScenePlan:
            plans = self._scene_plans(prompt)
            return plans[0]  # type: ignore[return-value]
        if schema is ShotPlan:
            return self._shot_plans(prompt)[0]  # type: ignore[return-value]
        if schema is DirectorPlan:
            return parse_director_plan(prompt, _FAKE_SELECTION["shot_id"])  # type: ignore[return-value]
        if schema is ProductionIntent:
            return parse_production_intent(prompt, _FAKE_SELECTION["shot_id"])  # type: ignore[return-value]
        raise NotImplementedError(f"FakeLLMGateway.structured unsupported schema: {schema}")

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        if schema is ScenePlan:
            return self._scene_plans(prompt)  # type: ignore[return-value]
        if schema is ShotPlan:
            return self._shot_plans(prompt)  # type: ignore[return-value]
        raise NotImplementedError(f"FakeLLMGateway.structured_list unsupported schema: {schema}")

    # --- deterministic heuristics ---

    def _scene_plans(self, prompt: str) -> list[ScenePlan]:
        # ~1 scene per 300 chars, 2..5 scenes; deterministic by text length
        n_scenes = max(2, min(5, math.ceil(len(prompt) / 300)))
        locations = ["城市街道", "室内客厅", "学校体育馆", "天台", "地下车库"]
        return [
            ScenePlan(
                scene_number=i + 1,
                title=f"场景 {i + 1}",
                location=locations[i % len(locations)],
                time="night" if i % 2 else "day",
                description=f"（FAKE 分析）该场景延续前文冲突，人物关系推进，节奏{'加快' if i % 2 else '平稳'}。",
                mood=_MOODS[i % len(_MOODS)],
            )
            for i in range(n_scenes)
        ]

    def _shot_plans(self, prompt: str) -> list[ShotPlan]:
        n_shots = 6
        return [
            ShotPlan(
                shot_number=i + 1,
                shot_type=_SHOT_TYPES[i % len(_SHOT_TYPES)],  # type: ignore[arg-type]
                camera_angle=_CAMERA_ANGLES[i % len(_CAMERA_ANGLES)],
                camera_movement=_MOVEMENTS[i % len(_MOVEMENTS)],
                duration=2.5 if i % 2 else 3.5,
                action=_ACTIONS[i % len(_ACTIONS)],
                emotion=_MOODS[i % len(_MOODS)],
                dialogue=f"（FAKE）第 {i + 1} 镜对白占位。" if i in (1, 4) else None,
                image_prompt=f"（FAKE prompt）{_SHOT_TYPES[i % len(_SHOT_TYPES)]} shot, {_ACTIONS[i % len(_ACTIONS)]}, manga style",
            )
            for i in range(n_shots)
        ]
