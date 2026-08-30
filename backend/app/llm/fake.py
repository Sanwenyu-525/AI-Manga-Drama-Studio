"""FakeLLMGateway — deterministic fake for tests and keyless development (mvp-spec §100, §101).

DEV-ONLY (不要用于生产): 作为测试与无 key 开发的默认实现。分析/分镜/连续性均为
关键词规则输出，**不代表真实模型质量**。切真实产品链路必须 `STUDIO_LLM_MODE=openai`
（LangChainOpenAIGateway）。两侧实现同一 LLMGateway 协议，业务代码无感知差异。

Returns heuristic but valid ScenePlan / ShotPlan so the whole Stage B chain
(analyze → preview → create scenes → generate shots → storyboard) runs without
any LLM API key. Switch with STUDIO_LLM_MODE=openai for real models.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Sequence
from typing import TypeVar

from pydantic import BaseModel

from app.agents.fake_planner import parse_director_plan, parse_production_intent
from app.core.logging import get_logger
from app.domain.agent import DirectorPlan, ProductionIntent
from app.domain.analysis import ScenePlan, ShotPlan
from app.domain.continuity import SemanticWarning
from app.llm.messages import ChatMessage, ChatOptions, ChatResponse, TokenUsage

logger = get_logger("llm.fake")

T = TypeVar("T", bound=BaseModel)


def selection_from_prompt(prompt: str) -> str | None:
    """Extract the first selected shot id from the understand prompt (run-local)."""
    import re

    m = re.search(r"shots=\[([^\]]*)\]", prompt)
    if not m:
        return None
    ids = [part.strip().strip("'\"") for part in m.group(1).split(",") if part.strip()]
    return ids[0] if ids else None

_MOODS = ["tense", "calm", "warm", "melancholic", "excited"]
_SHOT_TYPES = ["wide", "medium", "close_up", "extreme_close_up", "full", "medium"]
_CAMERA_ANGLES = ["eye_level", "low_angle", "high_angle", "eye_level", "eye_level", "low_angle"]
_MOVEMENTS = ["static", "static", "dolly", "pan", "handheld", "static"]
_ACTIONS = ["人物入场", "对话", "关键动作", "反应", "环境空镜", "情绪特写"]


class FakeLLMGateway:
    """Deterministic implementation of the LLMGateway protocol."""

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        options: ChatOptions | None = None,
    ) -> ChatResponse:
        """Message-shaped core: echoes the last user turn deterministically.

        Token usage is derived from text length — stable for tests, never a
        quality claim about real models.
        """
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            messages[-1].content if messages else "",
        )
        content = f"FAKE: {last_user[:120]}…"
        logger.info("fake chat (%d messages, len=%d)", len(messages), len(last_user))
        return ChatResponse(
            content=content,
            model="fake-chat",
            finish_reason="stop",
            usage=TokenUsage(
                input_tokens=sum(len(m.content) for m in messages),
                output_tokens=len(content),
            ),
        )

    async def invoke(self, system: str, prompt: str) -> str:
        response = await self.chat(
            [ChatMessage(role="system", content=system), ChatMessage(role="user", content=prompt)]
        )
        return response.content

    async def structured(self, schema: type[T], system: str, prompt: str) -> T:
        if schema is ScenePlan:
            plans = self._scene_plans(prompt)
            return plans[0]  # type: ignore[return-value]
        if schema is ShotPlan:
            return self._shot_plans(prompt)[0]  # type: ignore[return-value]
        if schema is DirectorPlan:
            return parse_director_plan(prompt, selection_from_prompt(prompt))  # type: ignore[return-value]
        if schema is ProductionIntent:
            return parse_production_intent(prompt, selection_from_prompt(prompt))  # type: ignore[return-value]
        raise NotImplementedError(f"FakeLLMGateway.structured unsupported schema: {schema}")

    async def structured_list(self, schema: type[T], system: str, prompt: str) -> list[T]:
        if schema is ScenePlan:
            return self._scene_plans(prompt)  # type: ignore[return-value]
        if schema is ShotPlan:
            return self._shot_plans(prompt)  # type: ignore[return-value]
        if schema is SemanticWarning:
            return self._semantic_continuity_warnings(prompt)  # type: ignore[return-value]
        raise NotImplementedError(f"FakeLLMGateway.structured_list unsupported schema: {schema}")

    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]:
        """Deterministic delta stream over invoke() output (tests / keyless dev)."""
        text = await self.invoke(system, prompt)
        for i in range(0, len(text), 8):
            yield text[i : i + 8]
            # 让出事件循环，模拟真实流式节奏（零等待，仅调度）
            await asyncio.sleep(0)

    # --- deterministic heuristics ---

    def _semantic_continuity_warnings(self, prompt: str) -> list:
        """P8-T018 fake semantic path: parse the scene shot-state JSON and emit a
        deterministic semantic warning (emotion/action across shot) so tests are
        stable without a live model."""
        import json as _json

        from app.domain.continuity import SemanticWarning

        try:
            data = _json.loads(prompt)
            states = data.get("scene_shots", [])
        except Exception:  # noqa: BLE001
            states = []
        out = []
        for idx, state in enumerate(states):
            nxt = states[idx + 1] if idx + 1 < len(states) else None
            if nxt is None:
                break
            cur_e = state.get("emotion")
            nxt_e = nxt.get("emotion")
            # heuristic: extreme emotion flip between adjacent shots = action_logic issue
            if cur_e and nxt_e and cur_e != nxt_e and {cur_e, nxt_e} <= {"tense", "calm"}:
                out.append(
                    SemanticWarning(
                        scope="shot",
                        shot_id=nxt["shot_id"],
                        category="action_logic",
                        message="情绪在同一场景相邻镜头间剧烈翻转，语义衔接可疑。",
                        severity="warning",
                        evidence={"rule": "fake_emotion_flip", "from_emotion": cur_e, "to_emotion": nxt_e},
                    )
                )
                break
        return out

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
