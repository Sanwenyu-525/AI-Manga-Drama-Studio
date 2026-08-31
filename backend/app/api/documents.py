"""SourceDocument API (database-v0.1 §32.6, api-event-contract §20.1, mvp-spec DOC-003).

Router → Service only (red line: no db.query business logic in routers).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.source_document import (
    SourceDocumentCreate,
    SourceDocumentRead,
    SourceDocumentUpdateRequest,
)
from app.services import DocumentService

router = APIRouter(tags=["documents"])


@router.get(
    "/projects/{project_id}/documents",
    response_model=list[SourceDocumentRead],
)
def list_documents(
    project_id: str,
    doc_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[SourceDocumentRead]:
    return DocumentService(db).list_documents(project_id, doc_type)


@router.post(
    "/projects/{project_id}/documents",
    response_model=SourceDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    project_id: str, data: SourceDocumentCreate, db: Session = Depends(get_db)
) -> SourceDocumentRead:
    return DocumentService(db).create_document(project_id, data)


@router.get("/documents/{document_id}", response_model=SourceDocumentRead)
def get_document(document_id: str, db: Session = Depends(get_db)) -> SourceDocumentRead:
    return DocumentService(db).get_document(document_id)


@router.patch("/documents/{document_id}", response_model=SourceDocumentRead)
def update_document(
    document_id: str, data: SourceDocumentUpdateRequest, db: Session = Depends(get_db)
) -> SourceDocumentRead:
    """Optimistic concurrency (§21/§88): body = {revision, patch}; 409 on mismatch."""
    return DocumentService(db).update_document(document_id, data.revision, data.patch)


@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    DocumentService(db).delete_document(document_id)
    return {"id": document_id, "deleted": True}
