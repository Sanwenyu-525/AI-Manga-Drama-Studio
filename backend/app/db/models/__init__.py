"""ORM models — import all models here so Base.metadata is complete (Alembic / create_all)."""

from app.db.models.agent import AgentChangeSet, AgentProposal, AgentRun
from app.db.models.analysis import AnalysisSnapshot
from app.db.models.asset import Asset
from app.db.models.continuity import SceneContinuityState, ShotContinuityState
from app.db.models.character import Character, CharacterVersion, ShotCharacter
from app.db.models.continuity import ContinuityWarning, ShotTransition
from app.db.models.costume import Costume
from app.db.models.episode import Episode
from app.db.models.location import Location, LocationVersion
from app.db.models.generation import Generation
from app.db.models.generation_io import GenerationInput, GenerationOutput
from app.db.models.project import Project
from app.db.models.project_setting import ProjectSetting
from app.db.models.prompt import Prompt, PromptVersion
from app.db.models.scene import Scene
from app.db.models.shot import Shot
from app.db.models.shot_visual_spec import ShotVisualSpec
from app.db.models.job import Job, JobTask, TaskDependency
from app.db.models.workflow import WorkflowTemplate, WorkflowVersion
from app.db.models.timeline import Timeline, TimelineClip, TimelineTrack
from app.db.models.source_document import SourceDocument
from app.db.models.episode_pipeline import EpisodePipeline

__all__ = [
    "AgentChangeSet",
    "AgentProposal",
    "AgentRun",
    "AnalysisSnapshot",
    "Asset",
    "Character",
    "SceneContinuityState",
    "ShotContinuityState",
    "CharacterVersion",
    "ContinuityWarning",
    "Costume",
    "Episode",
    "Location",
    "LocationVersion",
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
    "ShotTransition",
    "ShotVisualSpec",
    "WorkflowTemplate",
    "WorkflowVersion",
    "Timeline",
    "TimelineClip",
    "TimelineTrack",
    "SourceDocument",
    "EpisodePipeline",
    "Job",
    "JobTask",
    "TaskDependency",
]
