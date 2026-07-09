import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import metadata

job_runs = Table(
    "job_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("job_type", String, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("lock_key", String, nullable=True),
    Column("status", String, nullable=False, server_default="queued"),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("locked_by", String, nullable=True),
    Column("locked_at", DateTime(timezone=True), nullable=True),
    Column("scheduled_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("job_type", "idempotency_key", name="uq_job_runs_job_type_idempotency_key"),
    Index(
        "ix_job_runs_pending_scheduled_at",
        "scheduled_at",
        postgresql_where=text("status IN ('queued', 'retrying')"),
    ),
)
