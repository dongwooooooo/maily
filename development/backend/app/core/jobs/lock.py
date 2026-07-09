import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.jobs.models import job_runs


async def acquire_lock(
    connection: AsyncConnection,
    *,
    job_id: uuid.UUID,
    worker_id: str,
) -> bool:
    """Claim a queued job for a worker.

    Atomically transitions the job from queued -> running and sets
    locked_by/locked_at, but only if no other worker already holds
    the lock. Returns True if this call won the claim, False if the
    job was already locked (or not found/queued).
    """
    stmt = (
        update(job_runs)
        .where(job_runs.c.id == job_id)
        .where(job_runs.c.status == "queued")
        .where(job_runs.c.locked_by.is_(None))
        .values(
            status="running",
            locked_by=worker_id,
            locked_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
        )
        .returning(job_runs.c.id)
    )
    result = await connection.execute(stmt)
    return result.first() is not None
