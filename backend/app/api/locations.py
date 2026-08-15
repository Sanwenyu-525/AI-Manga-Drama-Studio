"""Location + LocationVersion API (database-v0.1 §6, api-event-contract §142/§143)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.location import (
    LocationCreate,
    LocationRead,
    LocationUpdateRequest,
    LocationVersionCreate,
    LocationVersionRead,
)
from app.services import LocationService, LocationVersionService

router = APIRouter(tags=["locations"])


@router.get("/projects/{project_id}/locations", response_model=list[LocationRead])
def list_locations(project_id: str, db: Session = Depends(get_db)) -> list[LocationRead]:
    return LocationService(db).list_locations(project_id)


@router.post(
    "/projects/{project_id}/locations",
    response_model=LocationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_location(project_id: str, data: LocationCreate, db: Session = Depends(get_db)) -> LocationRead:
    return LocationService(db).create_location(project_id, data)


@router.get("/locations/{location_id}", response_model=LocationRead)
def get_location(location_id: str, db: Session = Depends(get_db)) -> LocationRead:
    return LocationService(db).get_location(location_id)


@router.patch("/locations/{location_id}", response_model=LocationRead)
def update_location(
    location_id: str, data: LocationUpdateRequest, db: Session = Depends(get_db)
) -> LocationRead:
    """Optimistic concurrency: body = {revision, patch}; 409 on mismatch."""
    return LocationService(db).update_location(location_id, data.revision, data.patch)


@router.delete("/locations/{location_id}", status_code=status.HTTP_200_OK)
def delete_location(location_id: str, db: Session = Depends(get_db)) -> dict:
    LocationService(db).delete_location(location_id)
    return {"id": location_id, "deleted": True}


# --- P2-T009: LocationVersion --------------------------------------------

@router.get("/locations/{location_id}/versions", response_model=list[LocationVersionRead])
def list_location_versions(location_id: str, db: Session = Depends(get_db)) -> list[LocationVersionRead]:
    """All visual versions of a location, ordered by version_number (v1, v2, ...)."""
    return LocationVersionService(db).list_versions(location_id)


@router.post(
    "/locations/{location_id}/versions",
    response_model=LocationVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_location_version(
    location_id: str, data: LocationVersionCreate, db: Session = Depends(get_db)
) -> LocationVersionRead:
    """Register a new visual version (stale by default; activate to promote to MASTER)."""
    return LocationVersionService(db).create_version(location_id, data)


@router.post(
    "/locations/{location_id}/versions/{version_id}/activate",
    response_model=LocationVersionRead,
)
def activate_location_version(
    location_id: str, version_id: str, db: Session = Depends(get_db)
) -> LocationVersionRead:
    """Promote the version to active and point locations.master_version_id at it."""
    return LocationVersionService(db).activate_version(location_id, version_id)
