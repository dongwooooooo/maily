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
    """queued job을 worker가 claim한다.

    다른 worker가 아직 lock을 잡지 않은 경우에만 job을 queued -> running으로
    atomic하게 transition하고 locked_by/locked_at을 설정한다. 이 호출이 claim을 이기면
    True, job이 이미 locked였거나 not found/queued 상태가 아니면 False를 반환한다.
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
