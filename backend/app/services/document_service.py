"""DocumentService (database-v0.1 §32.6, mvp-spec DOC-002, api-event-contract §20.1).

Project-level setting-document archive (character_setting / worldview / outline /
novel_draft / other). Rules (same as CostumeService):
- update_document() bumps revision (optimistic concurrency, api-event-contract §21/§88).
- All mutations publish domain events AFTER commit (red line: commit then publish).
- Soft delete only (contract §89).
- doc_type must be one of DOCUMENT_TYPES (422); optional entity refs
  (character/location/costume) are validated (existence + same project, 404/422).
- source_hash = SHA-256 prefix of content (analysis-key style) — recomputed on
  content change; the Agent injection digest derives from it (mvp-spec DOC-004).
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Character, Costume, Location, Project, SourceDocument
from app.db.models.source_document import DOCUMENT_TYPES
from app.domain.source_document import (
    SourceDocumentCreate,
    SourceDocumentRead,
    SourceDocumentUpdate,
)
from app.events.bus import (
    EVENT_DOCUMENT_CREATED,
    EVENT_DOCUMENT_DELETED,
    EVENT_DOCUMENT_UPDATED,
    StudioEvent,
    bus,
)
from app.repositories import ProjectRepository, SourceDocumentRepository

UPDATE_FIELDS = (
    "doc_type",
    "title",
    "content",
    "character_id",
    "location_id",
    "costume_id",
    "status",
)

# nullable linkage fields — must be settable to None explicitly via model_fields_set.
NULLABLE_LINK_FIELDS = ("character_id", "location_id", "costume_id")

_SOURCE_HASH_LENGTH = 16

# Budgeted digest cap for Agent injection (mvp-spec DOC-004) — keep the analysis
# prompt lean; the source text is chunked in ScriptService (_ANALYSIS_CHUNK_CHARS).
DOCUMENT_DIGEST_CAP = 2000

_ELISION = "...[truncated]..."


def _budget_truncate(text: str, max_chars: int) -> str:
    """Head + tail retention (mirrors TokenBudget.truncate without an agents-layer import)."""
    if len(text) <= max_chars:
        return text
    avail = max_chars - len(_ELISION)
    if avail <= 0:
        return text[:max_chars]
    head = int(avail * 0.5)
    return text[:head] + _ELISION + text[-(avail - head):]


def content_source_hash(content: str) -> str:
    """SHA-256 prefix of the raw content (analysis-key style, mvp-spec DOC-002)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:_SOURCE_HASH_LENGTH]


def _to_read(doc: SourceDocument) -> SourceDocumentRead:
    return SourceDocumentRead(
        id=doc.id,
        project_id=doc.project_id,
        doc_type=doc.doc_type,
        title=doc.title,
        content=doc.content,
        character_id=doc.character_id,
        location_id=doc.location_id,
        costume_id=doc.costume_id,
        source_hash=doc.source_hash,
        status=doc.status,
        revision=doc.revision,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class DocumentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SourceDocumentRepository(session)
        self.projects = ProjectRepository(session)

    # --- reads ---

    def get_document(self, document_id: str) -> SourceDocumentRead:
        doc = self.repo.get(document_id)
        if doc is None:
            raise NotFoundError("Document does not exist.", {"document_id": document_id})
        return _to_read(doc)

    def list_documents(self, project_id: str, doc_type: str | None = None) -> list[SourceDocumentRead]:
        self._require_project(project_id)
        if doc_type:
            self._validate_doc_type(doc_type)
        return [_to_read(doc) for doc in self.repo.list_for_project(project_id, doc_type)]

    def render_digest(self, project_id: str, max_chars: int = DOCUMENT_DIGEST_CAP) -> str:
        """Budgeted setting-document digest for Agent injection (mvp-spec DOC-004).

        Read-only helper shared by ScriptService analysis and ContextResolver: renders
        "[doc_type] title\\ncontent" per document in stable order, capped at max_chars.
        Returns "" when the project has no documents, so prompts stay unchanged.
        """
        docs = self.repo.list_for_project(project_id)
        if not docs:
            return ""
        parts = [f"[{d.doc_type}] {d.title}\n{d.content or ''}" for d in docs]
        return _budget_truncate("\n\n".join(parts), max_chars)

    # --- writes ---

    def create_document(self, project_id: str, data: SourceDocumentCreate) -> SourceDocumentRead:
        self._require_project(project_id)
        self._validate_doc_type(data.doc_type)
        self._validate_links(data, project_id)
        doc = SourceDocument(
            project_id=project_id,
            doc_type=data.doc_type,
            title=data.title,
            content=data.content,
            character_id=data.character_id,
            location_id=data.location_id,
            costume_id=data.costume_id,
            source_hash=content_source_hash(data.content),
            status=data.status,
            revision=1,
        )
        self.repo.add(doc)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_DOCUMENT_CREATED,
                entity_type="document",
                entity_id=doc.id,
                project_id=project_id,
            )
        )
        return _to_read(doc)

    def update_document(
        self, document_id: str, revision: int, patch: SourceDocumentUpdate
    ) -> SourceDocumentRead:
        """Optimistic concurrency (ATOMIC conditional update — two stale writers can't both win)."""
        doc = self.repo.get(document_id)
        if doc is None:
            raise NotFoundError("Document does not exist.", {"document_id": document_id})

        if patch.doc_type is not None:
            self._validate_doc_type(patch.doc_type)
        self._validate_links(patch, doc.project_id)

        values: dict = {}
        changed: list[str] = []
        for field in UPDATE_FIELDS:
            if field in NULLABLE_LINK_FIELDS:
                # allow linkage refs to be cleared to None explicitly
                if field not in patch.model_fields_set:
                    continue
                values[field] = getattr(patch, field)
                changed.append(field)
                continue
            value = getattr(patch, field)
            if value is not None:
                values[field] = value
                changed.append(field)
        if not changed:
            return _to_read(doc)

        # recompute source_hash whenever content (or anything affecting the digest) changes
        new_content = values.get("content", doc.content)
        values["source_hash"] = content_source_hash(new_content)

        values["updated_at"] = datetime.now(UTC).isoformat()
        stmt = (
            update(SourceDocument)
            .where(
                SourceDocument.id == document_id,
                SourceDocument.revision == revision,
                SourceDocument.deleted_at.is_(None),
            )
            .values(revision=SourceDocument.revision + 1, **values)
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(stmt)
        if result.rowcount == 0:
            current = self.session.scalar(
                select(SourceDocument.revision).where(SourceDocument.id == document_id)
            )
            raise ConflictError(
                "Document was modified by another writer.",
                {
                    "document_id": document_id,
                    "expected_revision": revision,
                    "current_revision": current,
                },
            )
        self.session.commit()
        self.session.refresh(doc)
        bus.publish(
            StudioEvent(
                event_type=EVENT_DOCUMENT_UPDATED,
                entity_type="document",
                entity_id=doc.id,
                project_id=doc.project_id,
                payload={"revision": doc.revision, "changed_fields": changed},
            )
        )
        return _to_read(doc)

    def delete_document(self, document_id: str) -> None:
        """Soft delete (contract §89)."""
        doc = self.repo.get(document_id)
        if doc is None:
            raise NotFoundError("Document does not exist.", {"document_id": document_id})
        self.repo.delete(doc)
        self.session.commit()
        bus.publish(
            StudioEvent(
                event_type=EVENT_DOCUMENT_DELETED,
                entity_type="document",
                entity_id=doc.id,
                project_id=doc.project_id,
            )
        )

    # --- helpers ---

    def _require_project(self, project_id: str) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("Project does not exist.", {"project_id": project_id})
        return project

    @staticmethod
    def _validate_doc_type(doc_type: str) -> None:
        if doc_type not in DOCUMENT_TYPES:
            raise ValidationError(
                "Unknown document type.",
                {"doc_type": doc_type, "allowed": list(DOCUMENT_TYPES)},
            )

    def _validate_links(self, data: SourceDocumentCreate | SourceDocumentUpdate, project_id: str) -> None:
        """Optional entity refs must exist (not deleted) and belong to the same project."""
        pairs = (
            ("character_id", data.character_id, Character),
            ("location_id", data.location_id, Location),
            ("costume_id", data.costume_id, Costume),
        )
        for field, value, model in pairs:
            if value is None:
                continue
            entity = self.session.scalar(
                select(model).where(model.id == value, model.deleted_at.is_(None))
            )
            if entity is None:
                raise NotFoundError(
                    f"{model.__name__} does not exist.",
                    {field: value},
                )
            if entity.project_id != project_id:
                raise ValidationError(
                    f"{model.__name__} belongs to another project.",
                    {field: value, "project_id": project_id, "entity_project_id": entity.project_id},
                )
