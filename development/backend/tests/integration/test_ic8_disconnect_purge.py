"""W4/IC8 (docs/goals/backend-plans/_build-schedule.md) — disconnect→purge.

Real chain, through the actual dispatcher (not calling the orchestration
function directly — that's already covered in depth by
tests/domains/mail_sources/test_purge_disconnected_source_job.py):
mail_sources.disconnect_gmail_source (real producer) emits
gmail_source_disconnected -> dispatch queues purge_disconnected_source
(source-locked) -> running it purges the account's content across every
domain via the real PURGE_HANDLER chain.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from app.core.database import engine
from app.core.discovery import register_discovered_jobs
from app.core.jobs import registry
from app.core.jobs.dispatcher import run_job
from app.core.jobs.models import job_runs
from app.core.jobs.outbox_dispatcher import dispatch_pending_events
from app.core.jobs.wiring import ACTIVE_EVENT_CONSUMERS
from app.domains.identity.models import workspaces
from app.domains.mail_intake.models import gmail_messages
from app.domains.mail_sources.models import gmail_oauth_credentials
from app.domains.mail_sources.repository import get_connected_account
from app.domains.mail_sources.schemas import ConnectGmailSourceInput, DisconnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source, disconnect_gmail_source


@pytest.fixture(autouse=True)
def _registered_jobs():
    register_discovered_jobs()
    yield
    registry.clear()


async def test_disconnect_emits_and_dispatch_runs_purge() -> None:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))

    data = ConnectGmailSourceInput(
        workspace_id=workspace_id,
        gmail_address=f"user-{uuid.uuid4()}@gmail.com",
        access_token="ya29.a0-example-access-token",
        refresh_token="1//0g-example-refresh-token",
        scope="https://www.googleapis.com/auth/gmail.readonly",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async with engine.begin() as connection:
        source, _ = await connect_gmail_source(connection, data)

    message_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=source.id,
                gmail_message_id=f"gmail-{uuid.uuid4()}",
                gmail_thread_id=f"thread-{uuid.uuid4()}",
            )
        )

    async with engine.begin() as connection:
        await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=workspace_id, connected_account_id=source.id),
        )

    async with engine.begin() as connection:
        enqueued = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        rows = (await connection.execute(select(job_runs).where(job_runs.c.id.in_(enqueued)))).mappings().all()
    relevant = [r for r in rows if r["payload"].get("source_id") == str(source.id)]
    purge_jobs = [r for r in relevant if r["job_type"] == "purge_disconnected_source"]
    assert len(purge_jobs) == 1
    assert purge_jobs[0]["lock_key"] == f"source:{source.id}"

    async with engine.begin() as connection:
        status = await run_job(connection, job_id=purge_jobs[0]["id"], worker_id="ic8-test")
    assert status == "succeeded"

    async with engine.connect() as connection:
        message_rows = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().all()
        credential_rows = (
            await connection.execute(
                select(gmail_oauth_credentials).where(gmail_oauth_credentials.c.connected_account_id == source.id)
            )
        ).mappings().all()
        account = await get_connected_account(connection, connected_account_id=source.id)

    assert message_rows == []
    assert credential_rows == []
    assert account["status"] == "disconnected"
