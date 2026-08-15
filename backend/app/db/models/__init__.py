"""ORM models — import all models here so Base.metadata is complete (Alembic / create_all)."""

from app.db.models.asset import Asset
from app.db.models.character import Character, CharacterVersion, ShotCharacter
from app.db.models.episode import Episode
from app.db.models.generation import Generation
from app.db.models.generation_io import GenerationInput, GenerationOutput
from app.db.models.project import Project
from app.db.models.project_setting import ProjectSetting
from app.db.models.prompt import Prompt, PromptVersion
from app.db.models.scene import Scene
from app.db.models.shot import Shot
from app.db.models.workflow import WorkflowTemplate, WorkflowVersion

__all__ = [
    "Asset",
    "Character",
    "CharacterVersion",
    "Episode",
    "Generation",
    "GenerationInput",
    "GenerationOutput",
    "Project",
    "ProjectSetting",
    "Prompt",
    "PromptVersion",
    "Scene",
    "Shot",
    "ShotCharacter",
    "WorkflowTemplate",
    "WorkflowVersion",
]
