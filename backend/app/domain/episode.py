"""Episode DTOs (api-event-contract §13-15)."""

from pydantic import BaseModel

from app.domain.common import EpisodeStatus


class EpisodeCreate(BaseModel):
    title: str | None = None
    source_text: str | None = None


class EpisodeUpdate(BaseModel):
    title: str | None = None
    source_text: str | None = None
    script_text: str | None = None
    summary: str | None = None
    status: EpisodeStatus | None = None


class EpisodeRead(BaseModel):
    id: str
    project_id: str
    episode_number: int
    title: str | None
    source_text: str | None
    script_text: str | None
    summary: str | None
    status: str
    created_at: str
    updated_at: str
