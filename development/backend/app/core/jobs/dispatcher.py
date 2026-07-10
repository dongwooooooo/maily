import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.jobs import registry
from app.core.jobs.lock import acquire_lock
from app.core.jobs.models import job_runs
from app.core.jobs.retry import should_retry


async def run_job(connection: AsyncConnection, *, job_id: uuid.UUID, worker_id: str) -> str:
    """job_run row 하나를 claim하고 실행한다. 결과 status를 반환한다.

    다른 worker가 이미 job을 잡고 있으면 "locked", row가 없으면 "not_found",
    job_type에 등록된 handler가 없거나 retry가 소진됐으면 "failed", handler가
    raise했지만 retry 가능하면 "retrying", 그 외에는 "succeeded"다.
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
