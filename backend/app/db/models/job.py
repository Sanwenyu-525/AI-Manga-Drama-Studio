"""Job / JobTask / TaskDependency models (database-v0.1 §16.6, P5-E1).

A Job is a schedulable batch of generation work (e.g. "render all shots of a scene").
Each JobTask targets one shot and creates exactly one Generation (via GenerationService)
when its dependencies are satisfied. task_dependencies expresses a DAG: a task runs only
after every depends-on task reached 'completed' (a non-success dependency → dependency_failed).

P5-E3/E4: task_type is 'image' in MVP (video columns/states reserved); the dependency
constraint is optional (MVP creates image tasks with no deps, but the DAG machinery is
validated + exercised by tests).
"""

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

JOB_TYPES = ("SCENE_IMAGE", "SCENE_VIDEO")  # SCENE_VIDEO reserved (MVP: image only)

JOB_STATUSES = (
    "created",
    "queued",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
)

JOB_TASK_TYPES = ("image", "video")  # video reserved in MVP
JOB_TASK_STATUSES = (
    "queued",
    "running",
    "completed",
    "failed",
    "skipped",
    "dependency_failed",
    "cancelled",
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = uuid_pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False, default="SCENE_IMAGE")
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id"), index=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    error_summary: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class JobTask(Base):
    __tablename__ = "job_tasks"
    __table_args__ = (
        Index("idx_job_tasks_job_status_priority", "job_id", "status", "priority"),
    )

    id: Mapped[str] = uuid_pk()
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(Text, nullable=False, default="image")
    target_type: Mapped[str] = mapped_column(Text, nullable=False, default="shot")
    target_id: Mapped[str] = mapped_column(ForeignKey("shots.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # shot_order
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_id: Mapped[str | None] = mapped_column(
        ForeignKey("generations.id"), index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class TaskDependency(Base):
    """DAG edge: task -> depends_on_task. PK = (task_id, depends_on_task_id) => each pair
    can appear once; a task may have many dependencies (fan-in) and be a dependency of
    many tasks (fan-out)."""

    __tablename__ = "task_dependencies"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("job_tasks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    depends_on_task_id: Mapped[str] = mapped_column(
        ForeignKey("job_tasks.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    created_at: Mapped[str] = ts_created()
