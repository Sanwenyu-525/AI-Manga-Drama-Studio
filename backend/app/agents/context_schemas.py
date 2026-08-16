"""ContextSchemas (P7-T007) — structured LLM context inputs & outputs.

The context passed to an LLM is validated into a Pydantic schema before it can be
consumed, so garbage/malformed context is rejected at the boundary instead of
leaking into the model. StoryContext renders a plain-text block for prompts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SceneBrief(BaseModel):
    id: str
    scene_number: int
    name: str | None = None


class StoryContext(BaseModel):
    """Validated structured context for story/scene planning (P7-T007)."""

    project_id: str
    scenes: list[SceneBrief] = Field(default_factory=list)

    def render_text(self) -> str:
        lines = ["Story context for project " + self.project_id]
        for s in self.scenes:
            lines.append("scene=" + str(s.scene_number) + ":" + (s.name or s.id))
        return "\n".join(lines)


class ShotPlanningContext(BaseModel):
    project_id: str
    shot_id: str | None = None
    scene_id: str | None = None
    text: str = ""
    token_chars: int = 0
