"""WorkflowTemplate / WorkflowVersion models (P4-T004, database-v0.1 §23-24).

Read-only catalog registry: the local ComfyUI template directory (workflows/*.json)
is snapshotted into the DB as workflow_templates + immutable workflow_versions
(SHA-256 file hash). The router only serves what the registry has registered.
"""

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.columns import ts_created, ts_updated, uuid_pk

WORKFLOW_TYPES = ("image", "video")

WORKFLOW_VERSION_STATUSES = ("active", "superseded", "archived")


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"
    __table_args__ = (
        UniqueConstraint("workflow_id", "workflow_type", name="uq_workflow_templates_workflow"),
    )

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_type: Mapped[str] = mapped_column(Text, nullable=False, default="image")
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False)  # JSON file id (filename stem)
    active_version_id: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = ts_created()
    updated_at: Mapped[str] = ts_updated()


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version_number", name="uq_workflow_versions_template_version"),
    )

    id: Mapped[str] = uuid_pk()
    template_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)  # SHA-256 of the template file
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # relative path to workflows_dir
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")

    created_at: Mapped[str] = ts_created()
