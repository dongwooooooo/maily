"""IC1 (docs/goals/backend-plans/_build-schedule.md) — 연결 -> sync.

mail_sources.connect_gmail_source(real producer, seed 아님)가 gmail_source_connected를
emit한다 -> core outbox dispatcher가 register_watch와 sync_full을 queue한다
(app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS 기준, IC별로 curated activation table이며
아직 다른 domain의 unwired declared intent까지 포함하는 raw discovery-collected map이 아님)
-> 이 job을 fake Gmail mailbox 대상으로 실행하면 실제 watch registration과 message snapshot이
생긴다. 이것은 end-to-end로 wired된 첫 cross-domain flow다. 다른 domain integration
checkpoint(IC2-IC8)는 모두 같은 dispatcher를 재사용하고, 여기서 같은 방식으로 입증된 뒤
자기 entry를 wiring.ACTIVE_EVENT_CONSUMERS에 추가한다.
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
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_messages, gmail_watch_registrations
from app.domains.mail_sources.schemas import ConnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source


async def _seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


@pytest.fixture(autouse=True)
def _registered_jobs():
    register_discovered_jobs()
    yield
    registry.clear()


async def test_connect_queues_register_watch_and_sync_full_and_both_run() -> None:
    workspace_id = await _seed_workspace()
    data = ConnectGmailSourceInput(
        workspace_id=workspace_id,
        gmail_address=f"user-{uuid.uuid4()}@gmail.com",
        access_token="ya29.a0-example-access-token",
        refresh_token="1//0g-example-refresh-token",
        scope="https://www.googleapis.com/auth/gmail.readonly",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async with engine.begin() as connection:
        source, is_new = await connect_gmail_source(connection, data)
    assert is_new is True

    reader = FakeGmailReader()
    reader.seed_mailbox(
        source.id,
        messages=[
            FakeMessage(gmail_message_id="msg-ic1-1", gmail_thread_id="thread-ic1-1"),
            FakeMessage(gmail_message_id="msg-ic1-2", gmail_thread_id="thread-ic1-2"),
        ],
        history_id=5,
    )
    set_reader(reader)

    # dispatch_pending_events는 system-wide pending event를 모두 처리한다(real dispatcher
    # poll loop도 마찬가지). 이 test의 Postgres는 suite 전체에서 공유되고 per-test rollback이
    # 없으므로, 다른 test가 남긴 pending outbox row(무관한 event type)도 여기서 dispatch될 수
    # 있다. 전체 dispatched set 대신 이 test의 source_id를 담은 row로 assertion scope를 좁힌다.
    async with engine.begin() as connection:
        enqueued_job_ids = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)

    async with engine.connect() as connection:
        all_queued = (
            (await connection.execute(select(job_runs).where(job_runs.c.id.in_(enqueued_job_ids))))
            .mappings()
            .all()
        )
    queued = [row for row in all_queued if row["payload"].get("source_id") == str(source.id)]
    queued_job_types = {row["job_type"] for row in queued}
    assert queued_job_types == {"register_watch", "sync_full"}
    for row in queued:
        assert row["lock_key"] == f"source:{source.id}"

    for row in queued:
        async with engine.begin() as connection:
            status = await run_job(connection, job_id=row["id"], worker_id="ic1-test")
        assert status == "succeeded"

    async with engine.connect() as connection:
        watch_rows = (
            await connection.execute(
                select(gmail_watch_registrations).where(
                    gmail_watch_registrations.c.connected_account_id == source.id
                )
            )
        ).mappings().all()
        message_rows = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == source.id)
            )
        ).mappings().all()

    assert len(watch_rows) == 1
    assert len(message_rows) == 2
