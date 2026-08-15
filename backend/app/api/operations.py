"""Operation API (api-event-contract §15, §81): poll status of background AI operations."""

from fastapi import APIRouter

from app.operations.store import operation_store

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/{operation_id}")
def get_operation(operation_id: str) -> dict:
    return operation_store.get(operation_id)
