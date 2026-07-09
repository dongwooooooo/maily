import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.jobs import registry
from app.core.jobs.lock import acquire_lock
from app.core.jobs.models import job_runs
from app.core.jobs.retry import should_retry


async def run_job(connection: AsyncConnection, *, job_id: uuid.UUID, worker_id: str) -> str:
    """Claim and execute one job_run row. Returns the resulting status.

    "locked" if another worker already holds the job, "not_found" if
    the row doesn't exist, "failed" if no handler is registered for
    its job_type or retries are exhausted, "retrying" if the handler
    raised but may be retried, "succeeded" otherwise.
    """
    locked = await acquire_lock(connection, job_id=job_id, worker_id=worker_id)
    if not locked:
        return "locked"

    row = (
        await connection.execute(select(job_runs).where(job_runs.c.id == job_id))
    ).mappings().first()
    if row is None:
        return "not_found"

    handler = registry.get_handler(row["job_type"])
    if handler is None:
        await connection.execute(
            update(job_runs)
            .where(job_runs.c.id == job_id)
            .values(status="failed", finished_at=datetime.now(timezone.utc))
        )
        return "failed"

    try:
        await handler(row["payload"])
    except Exception:
        attempt_count = row["attempt_count"] + 1
        next_status = "retrying" if should_retry(attempt_count) else "failed"
        await connection.execute(
            update(job_runs)
            .where(job_runs.c.id == job_id)
            .values(
                status=next_status,
                attempt_count=attempt_count,
                locked_by=None,
                locked_at=None,
                finished_at=datetime.now(timezone.utc) if next_status == "failed" else None,
            )
        )
        return next_status

    await connection.execute(
        update(job_runs)
        .where(job_runs.c.id == job_id)
        .values(status="succeeded", finished_at=datetime.now(timezone.utc))
    )
    return "succeeded"
