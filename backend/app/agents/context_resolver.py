"""ContextResolver (P7-T005) — build typed, budgeted context for LLM calls.

The Director's load_context node currently uses ContextService.get_shot_context()
(Selection-aware minimum context). ContextResolver generalizes this by context_type:
story_planning / shot_planning / prompt each carry different facts (design
ai-director-agent §24-32). All output goes through TokenBudget before it reaches
an LLM, so no call exceeds the prompt cap (P7-T006).

Red line: the resolver only READS studio Services — it never mutates domain state.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.context_schemas import StoryContext
from app.agents.token_budget import TokenBudget
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.models import Episode, Scene, Shot
from app.services.context_service import ContextService

logger = get_logger("agent.context")

CONTEXT_STORY_PLANNING = "story_planning"
CONTEXT_SHOT_PLANNING = "shot_planning"
CONTEXT_PROMPT = "prompt"


class ContextResolver:
    """Builds minimal-but-sufficient context strings for different planning stages."""

    def __init__(self, session: Session, max_chars: int | None = None) -> None:
        self.session = session
        self.context_service = ContextService(session)
        self.budget = TokenBudget(max_chars) if max_chars else TokenBudget()

    def resolve(self, context_type, project_id, *, shot_id=None, scene_id=None):
        """Resolve a typed context payload as a plain dict for the graph state."""
        if context_type == CONTEXT_STORY_PLANNING:
            return self._story_planning(project_id)
        if context_type == CONTEXT_SHOT_PLANNING:
            return self._shot_planning(project_id, shot_id, scene_id)
        if context_type == CONTEXT_PROMPT:
            return self._prompt_context(project_id, shot_id)
        raise NotFoundError("Unknown context_type.", {"context_type": context_type})

    def _shot_planning(self, project_id, shot_id, scene_id):
        target = shot_id
        if target is None and scene_id:
            from sqlalchemy import select
            shots = list(self.session.scalars(
                select(Shot).where(Shot.scene_id == scene_id, Shot.deleted_at.is_(None)).order_by(Shot.shot_order)
            ))
            if shots:
                target = shots[0].id
        shot_ctx = {}
        if target:
            shot_ctx = self.context_service.get_shot_context(target)
        raw = self._render_shot_planning(project_id, shot_ctx, scene_id)
        budgeted = self.budget.truncate(raw)
        return {"context_type": CONTEXT_SHOT_PLANNING, "shot_id": target, "scene_id": scene_id, "text": budgeted, "token_chars": len(budgeted)}

    def _story_planning(self, project_id):
        scenes = _scene_briefs(self.session, self._scenes_of(project_id))
        model = StoryContext(project_id=project_id, scenes=scenes)
        budgeted = self.budget.truncate(model.render_text())
        return {"context_type": CONTEXT_STORY_PLANNING, "project_id": project_id, "text": budgeted, "token_chars": len(budgeted)}

    def _prompt_context(self, project_id, shot_id):
        if not shot_id:
            raise NotFoundError("prompt context requires a shot id.")
        shot_ctx = self.context_service.get_shot_context(shot_id)
        spec = self._shot_spec(shot_id)
        raw = self._render_prompt(project_id, shot_ctx, spec)
        budgeted = self.budget.truncate(raw)
        return {"context_type": CONTEXT_PROMPT, "project_id": project_id, "shot_id": shot_id, "text": budgeted, "token_chars": len(budgeted)}

    def _scenes_of(self, project_id):
        from sqlalchemy import select
        return select(Scene).join(Episode).where(Episode.project_id == project_id, Scene.deleted_at.is_(None)).order_by(Scene.scene_number)

    def _render_shot_planning(self, project_id, shot_ctx, scene_id):
        lines = ["Project " + project_id, "Scene " + str(scene_id or (shot_ctx.get("scene") or {}).get("id"))]
        shot = shot_ctx.get("shot")
        if shot:
            fields = [k + "=" + str(v) for k, v in shot.items() if k != "id" and v is not None]
            lines.append("Shot: " + ", ".join(fields))
        scene = shot_ctx.get("scene")
        if scene:
            lines.append("Scene meta: " + ", ".join(str(k) + "=" + str(v) for k, v in scene.items()))
        neighbors = shot_ctx.get("neighbors") or {}
        if neighbors.get("previous"):
            lines.append("prev=" + str(neighbors.get("previous")))
        if neighbors.get("next"):
            lines.append("next=" + str(neighbors.get("next")))
        gens = shot_ctx.get("recent_generations") or []
        if gens:
            lines.append("recent_generations=" + "; ".join(g["status"] + ":" + g["type"] for g in gens))
        return "\n".join(lines)

    def _render_prompt(self, project_id, shot_ctx, spec):
        lines = ["Project " + project_id, "Prompt-building context"]
        shot = shot_ctx.get("shot") or {}
        lines.append("Shot(shot_type=" + str(shot.get("shot_type")) + ", camera_angle=" + str(shot.get("camera_angle")) + ", emotion=" + str(shot.get("emotion")) + ")")
        if spec:
            lines.append("ShotVisualSpec=" + str(spec))
        if shot.get("image_prompt"):
            lines.append("image_prompt=" + shot["image_prompt"])
        return "\n".join(lines)

    def _shot_spec(self, shot_id):
        from app.db.models import ShotVisualSpec
        spec = self.session.get(ShotVisualSpec, shot_id)
        return spec.mapped_read_dict() if spec is not None else None


def _scene_briefs(session, stmt):
    return [{"id": s.id, "scene_number": s.scene_number, "name": s.name} for s in session.scalars(stmt)]
