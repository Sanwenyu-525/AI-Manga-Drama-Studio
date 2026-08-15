"""Pydantic domain schemas — the DTO contract between API/Service and Frontend.

Conventions (api-event-contract): REST returns plain DTOs; errors via {error:{...}}.
Pydantic models are also the data contract for LLM structured output (Stage B+).
"""

from app.domain.episode import (
    EpisodeCreate,
    EpisodeRead,
    EpisodeUpdate,
)
from app.domain.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from app.domain.scene import (
    SceneCreate,
    SceneRead,
    SceneSummary,
    SceneUpdate,
)
from app.domain.shot import (
    ShotCreate,
    ShotRead,
    ShotSummary,
    ShotUpdate,
    ShotUpdateRequest,
    StoryboardRead,
)

__all__ = [
    "EpisodeCreate",
    "EpisodeRead",
    "EpisodeUpdate",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "SceneCreate",
    "SceneRead",
    "SceneSummary",
    "SceneUpdate",
    "ShotCreate",
    "ShotRead",
    "ShotSummary",
    "ShotUpdate",
    "ShotUpdateRequest",
    "StoryboardRead",
]
