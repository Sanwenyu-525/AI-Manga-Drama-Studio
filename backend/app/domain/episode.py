"""Episode DTOs (api-event-contract §13-15)."""

from pydantic import BaseModel, Field

from app.domain.common import EpisodeStatus


class EpisodeCreate(BaseModel):
    title: str | None = None
    source_text: str | None = None


class EpisodeUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    title: str | None = None
    source_text: str | None = None
    script_text: str | None = None
    summary: str | None = None
    status: EpisodeStatus | None = None


class EpisodeUpdateRequest(BaseModel):
    """Optimistic concurrency (api-event-contract §21/§88): {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: EpisodeUpdate


class EpisodeRead(BaseModel):
    id: str
    project_id: str
    episode_number: int
    title: str | None
    source_text: str | None
    script_text: str | None
    summary: str | None
    status: str
    revision: int
    created_at: str
    updated_at: str
