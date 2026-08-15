"""Job DTOs (api-event-contract §142/§143, P5-E1/E2)."""

from pydantic import BaseModel, Field

from typing import Literal


class JobCreate(BaseModel):
    """POST /projects/{id}/jobs body — create a scene generation job."""

    scene_id: str
    name: str | None = None


class JobTaskRead(BaseModel):
    """One work item of a job (task_type image in MVP; video reserved)."""

    id: str
    job_id: str
    task_type: Literal["image", "video"]
    target_type: Literal["shot"]
    target_id: str
    shot_id: str
    status: str
    priority: int
    progress: int
    generation_id: str | None
    error_message: str | None
    created_at: str
    updated_at: str


class JobRead(BaseModel):
    """Job summary + task summaries (POST/create and GET single include tasks)."""

    id: str
    project_id: str
    name: str
    job_type: str
    scene_id: str | None
    status: str
    progress: int
    error_summary: str | None
    created_at: str
    updated_at: str
    task_count: int
    task_status_counts: dict[str, int] = Field(default_factory=dict)
    tasks: list[JobTaskRead] = Field(default_factory=list)


class JobSummaryRead(BaseModel):
    """Lightweight job row for project listing (no embedded tasks)."""

    id: str
    project_id: str
    name: str
    job_type: str
    scene_id: str | None
    status: str
    progress: int
    error_summary: str | None
    task_count: int
    created_at: str
    updated_at: str
