"""Read Model DTOs (P2-T011/T012/T013).

Formalized, aggregate read shapes for the Studio UI that complement (not duplicate)
the existing workspace-boot (bootstrap §103-104) and per-scene grid (storyboard
§101-102) endpoints:

- P2-T011 GET /projects/{id}/tree  — whole project navigation hierarchy in one call.
- P2-T012 GET /scenes/{id}/editor   — a scene plus its shots with visual-spec summary.
- P2-T013 GET /shots/{id}/inspector — full shot detail (visual spec + active versions
  + prompt version summary + cast with costume).

Routers stay logic-free (AGENTS.md §3): payloads are assembled by ReadModelService.
"""
from pydantic import BaseModel, Field

from app.domain.project import ProjectRead
from app.domain.scene import SceneRead
from app.domain.shot import ShotRead
from app.domain.shot_visual_spec import ShotVisualSpecRead


# ---------------------------------------------------------------- tree ----------

class ShotTreeItem(BaseModel):
    """Shot summary row in the project tree (P2-T011)."""

    id: str
    shot_number: int
    shot_type: str
    status: str
    dirty_state: str
    revision: int
    active_image_version: int | None = None
    active_video_version: int | None = None
    active_prompt_version_id: str | None = None


class SceneTreeItem(BaseModel):
    """Scene summary row with its shot summaries (P2-T011)."""

    id: str
    scene_number: int
    name: str | None
    shot_count: int = 0
    shots: list[ShotTreeItem] = Field(default_factory=list)


class EpisodeTreeItem(BaseModel):
    """Episode summary row with its scenes (P2-T011)."""

    id: str
    episode_number: int
    title: str | None
    scene_count: int = 0
    scenes: list[SceneTreeItem] = Field(default_factory=list)


class ProjectTreeRead(BaseModel):
    """Full project navigation tree (P2-T011): project + episodes(scene_count) +
    scenes(shot_count) + shot summaries, returned in one call."""

    project: ProjectRead
    episodes: list[EpisodeTreeItem] = Field(default_factory=list)


# ---------------------------------------------------------------- editor --------

class ShotEditorItem(BaseModel):
    """Shot row for the scene editor (P2-T012): visual-spec summary + active versions."""

    id: str
    shot_number: int
    shot_type: str
    status: str
    dirty_state: str
    duration: float | None
    revision: int
    title: str | None = None
    spec_summary: dict = Field(default_factory=dict)  # camera_angle/camera_movement/composition/...
    active_image_version: int | None = None
    active_video_version: int | None = None
    character_names: list[str] = Field(default_factory=list)


class SceneEditorRead(BaseModel):
    """Scene editor payload (P2-T012): the scene plus its shots with spec summary."""

    scene: SceneRead
    shots: list[ShotEditorItem] = Field(default_factory=list)


# ---------------------------------------------------------------- inspector -----

class InspectorCharacter(BaseModel):
    """A character cast in the shot, with per-shot costume/role/pose (P2-T013)."""

    character_id: str
    name: str
    alias: str | None = None
    master_version_id: str | None = None
    costume_id: str | None = None        # per-shot link costume (shot_characters)
    role: str | None = None              # per-shot link role
    position: str | None = None          # per-shot link position
    pose: str | None = None              # per-shot link pose


class InspectorPromptVersionSummary(BaseModel):
    """Prompt version summary for the inspector (P2-T013): authoritative active +
    count, per prompt_type (ADR-002)."""

    active_version: int | None = None
    version_count: int = 0
    prompt_id: str | None = None


class ShotInspectorRead(BaseModel):
    """Shot inspector payload (P2-T013): full shot + visual spec + active versions +
    prompt version summary + cast with costume."""

    shot: ShotRead
    visual_spec: ShotVisualSpecRead
    active_image_version: int | None = None
    active_video_version: int | None = None
    active_prompt_version_id: str | None = None
    prompts: dict[str, InspectorPromptVersionSummary] = Field(default_factory=dict)
    characters: list[InspectorCharacter] = Field(default_factory=list)
