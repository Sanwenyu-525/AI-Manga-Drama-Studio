"""Job API (api-event-contract §142/§143, P5-E2/E3) — thin Router → Service.

No business logic in the router (red line): it only serializes Service results.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.job import JobCreate, JobRead, JobSummaryRead
from app.services import JobService

router = APIRouter(tags=["jobs"])


@router.post("/projects/{project_id}/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(project_id: str, data: JobCreate, db: Session = Depends(get_db)) -> JobRead:
    """Create a scene generation job (P5-E1: one image task per live shot)."""
    job = JobService(db).create_scene_job(data.scene_id, data.name)
    return JobService(db).get_job(job.id)


@router.get("/projects/{project_id}/jobs", response_model=list[JobSummaryRead])
def list_jobs(project_id: str, db: Session = Depends(get_db)) -> list[JobSummaryRead]:
    """Job summaries for a project (no embedded tasks)."""
    return JobService(db).list_jobs(project_id)


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    return JobService(db).get_job(job_id)


@router.post("/jobs/{job_id}/pause", response_model=JobRead)
def pause_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    return JobService(db).pause_job(job_id)


@router.post("/jobs/{job_id}/resume", response_model=JobRead)
def resume_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    return JobService(db).resume_job(job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobRead)
def retry_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    return JobService(db).retry_job(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    """Cancel a job: unfinished tasks → cancelled; running generations are interrupted
    via the existing worker cancel path (best-effort provider interrupt)."""
    job_read, running_gen_ids = JobService(db).cancel_job(job_id)
    if running_gen_ids:
        from app.generations.worker import cancel_running

        for gid in running_gen_ids:
            await cancel_running(gid)
    return job_read
