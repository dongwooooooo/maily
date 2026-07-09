import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert, select

from app.core.database import engine
from app.core.jobs import registry
from app.core.jobs.dispatcher import run_job
from app.core.jobs.lock import acquire_lock
from app.core.jobs.models import job_runs


@pytest.fixture(autouse=True)
def _clear_registry():
    yield
    registry.clear()


async def _insert_queued_job(job_type: str, payload: dict) -> uuid.UUID:
    job_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(job_runs).values(
                id=job_id,
                job_type=job_type,
                payload=payload,
                idempotency_key=str(uuid.uuid4()),
                status="queued",
                scheduled_at=datetime.now(timezone.utc),
            )
        )
    return job_id


async def test_acquire_lock_lets_only_one_worker_win_concurrent_claim() -> None:
    job_id = await _insert_queued_job("noop", {})

    async def claim(worker_id: str) -> bool:
        async with engine.begin() as connection:
            return await acquire_lock(connection, job_id=job_id, worker_id=worker_id)

    results = await asyncio.gather(claim("worker-a"), claim("worker-b"))

    assert sorted(results) == [False, True]


async def test_run_job_calls_registered_handler_and_marks_succeeded() -> None:
    received_payloads = []

    async def handler(payload: dict) -> None:
        received_payloads.append(payload)

    registry.register("send_welcome_email", handler)
    job_id = await _insert_queued_job("send_welcome_email", {"to": "a@example.com"})

    async with engine.begin() as connection:
        status = await run_job(connection, job_id=job_id, worker_id="worker-a")

    assert status == "succeeded"
    assert received_payloads == [{"to": "a@example.com"}]

    async with engine.begin() as connection:
        stored_status = (
            await connection.execute(select(job_runs.c.status).where(job_runs.c.id == job_id))
        ).scalar_one()
    assert stored_status == "succeeded"


async def test_run_job_marks_retrying_and_increments_attempt_count_when_handler_raises() -> None:
    async def failing_handler(payload: dict) -> None:
        raise RuntimeError("boom")

    registry.register("always_fails", failing_handler)
    job_id = await _insert_queued_job("always_fails", {})

    async with engine.begin() as connection:
        status = await run_job(connection, job_id=job_id, worker_id="worker-a")

    assert status == "retrying"

    async with engine.begin() as connection:
        attempt_count = (
            await connection.execute(
                select(job_runs.c.attempt_count).where(job_runs.c.id == job_id)
            )
        ).scalar_one()
    assert attempt_count == 1


async def test_run_job_returns_locked_when_already_claimed() -> None:
    job_id = await _insert_queued_job("noop", {})
    async with engine.begin() as connection:
        await acquire_lock(connection, job_id=job_id, worker_id="worker-a")

    async with engine.begin() as connection:
        status = await run_job(connection, job_id=job_id, worker_id="worker-b")

    assert status == "locked"


def test_registry_rejects_duplicate_job_type_registration() -> None:
    async def handler(payload: dict) -> None:
        return None

    registry.register("dup", handler)

    with pytest.raises(registry.DuplicateJobTypeError):
        registry.register("dup", handler)
