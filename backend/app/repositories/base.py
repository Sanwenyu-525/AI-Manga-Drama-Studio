"""Generic SQLAlchemy repository base.

Repositories are the ONLY layer that touches the ORM session for queries.
Services depend on repositories; routers depend on services (red line: no db.query in routers).
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base

M = TypeVar("M", bound=Base)


class SQLAlchemyRepository(Generic[M]):
    model: type[M]

    def __init__(self, session: Session) -> None:
        self.session = session

    # --- reads (soft-delete aware) ---

    def get(self, entity_id: str) -> M | None:
        stmt = select(self.model).where(
            self.model.id == entity_id, self.model.deleted_at.is_(None)
        )
        return self.session.scalars(stmt).first()

    def get_or_none(self, entity_id: str) -> M | None:
        return self.get(entity_id)

    def list_all(self, **filters: Any) -> list[M]:
        stmt = select(self.model).where(self.model.deleted_at.is_(None))
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        return list(self.session.scalars(stmt))

    def list_ordered(self, order_by: str = "created_at", **filters: Any) -> list[M]:
        stmt = select(self.model).where(self.model.deleted_at.is_(None))
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        stmt = stmt.order_by(getattr(self.model, order_by))
        return list(self.session.scalars(stmt))

    def next_sequence(self, parent_field: str, parent_id: str, seq_field: str) -> int:
        """Return max(seq_field)+1 within a parent scope (e.g. next shot_number in scene)."""
        from sqlalchemy import func

        stmt = (
            select(func.max(getattr(self.model, seq_field)))
            .where(
                getattr(self.model, parent_field) == parent_id,
                self.model.deleted_at.is_(None),
            )
        )
        current = self.session.scalar(stmt)
        return (current or 0) + 1

    # --- writes ---

    def add(self, entity: M) -> M:
        self.session.add(entity)
        return entity

    def delete(self, entity: M) -> None:
        """Soft delete (database-v0.1 §41): set deleted_at, never hard-delete core entities."""
        from app.db.models.columns import utcnow_iso

        entity.deleted_at = utcnow_iso()
