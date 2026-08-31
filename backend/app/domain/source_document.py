"""SourceDocument DTOs (database-v0.1 §32.6, api-event-contract §20.1).

Follows the Character DTO pattern: revision + soft delete (§21/§88-89), so
PATCH takes {revision, patch} and 409s on a stale revision.
"""

from pydantic import BaseModel, Field

from app.db.models.source_document import DOCUMENT_TYPES


class SourceDocumentCreate(BaseModel):
    doc_type: str = Field(default="other", max_length=50)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(default="", max_length=200_000)
    character_id: str | None = None
    location_id: str | None = None
    costume_id: str | None = None
    status: str = "active"


class SourceDocumentUpdate(BaseModel):
    """Patch payload — every field optional; None means 'leave unchanged'."""

    doc_type: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=200_000)
    character_id: str | None = None
    location_id: str | None = None
    costume_id: str | None = None
    status: str | None = None


class SourceDocumentUpdateRequest(BaseModel):
    """Optimistic concurrency (§21/§88): {revision, patch}; 409 on mismatch."""

    revision: int = Field(ge=1)
    patch: SourceDocumentUpdate


class SourceDocumentRead(BaseModel):
    id: str
    project_id: str
    doc_type: str
    title: str
    content: str
    character_id: str | None
    location_id: str | None
    costume_id: str | None
    source_hash: str | None
    status: str
    revision: int
    created_at: str
    updated_at: str


# Re-export for callers that only care about the allowed types.
__all__ = [
    "DOCUMENT_TYPES",
    "SourceDocumentCreate",
    "SourceDocumentUpdate",
    "SourceDocumentUpdateRequest",
    "SourceDocumentRead",
]
