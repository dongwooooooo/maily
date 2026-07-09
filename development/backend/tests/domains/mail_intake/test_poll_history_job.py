import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.database import engine
from app.core.jobs.models import job_runs
from app.domains.mail_intake import repository, service
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_sync_cursors
from tests.domains.mail_intake.conftest import seed_connected_account


async def _seed_synced_account(*, history_id: int = 10) -> tuple[uuid.UUID, FakeGmailReader]:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(account_id, messages=[], history_id=history_id)
    set_reader(reader)
    async with engine.begin() as connection:
        await service.sync_full(connection, connected_account_id=account_id, reason="initial")
    return account_id, reader


async def test_poll_selects_stale_sources() -> None:
    now = datetime.now(timezone.utc)
    stale_account, _ = await _seed_synced_account()
    fresh_account, _ = await _seed_synced_account()

    async with engine.begin() as connection:
        await connection.execute(
            update(gmail_sync_cursors)
            .where(gmail_sync_cursors.c.connected_account_id == stale_account)
            .values(last_successful_sync_at=now - timedelta(hours=1))
        )
        await connection.execute(
            update(gmail_sync_cursors)
            .where(gmail_sync_cursors.c.connected_account_id == fresh_account)
            .values(last_successful_sync_at=now)
        )

    async with engine.connect() as connection:
        stale_targets = await repository.list_sources_for_polling(
            connection, stale_before=now - timedelta(minutes=10)
        )

    stale_ids = {row["connected_account_id"] for row in stale_targets}
    assert stale_account in stale_ids
    assert fresh_account not in stale_ids


async def test_poll_queues_delta_on_change() -> None:
    account_id, reader = await _seed_synced_account(history_id=10)
    reader.push_history(
        account_id,
        record_type="message_added",
        message=FakeMessage(gmail_message_id="msg-new", gmail_thread_id="thread-new"),
    )

    async with engine.begin() as connection:
        result = await service.poll_history(connection, connected_account_id=account_id)

    assert result["queued_delta"] is True

    async with engine.connect() as connection:
        jobs = (
            await connection.execute(select(job_runs).where(job_runs.c.job_type == "sync_delta"))
        ).mappings().all()
    assert any(uuid.UUID(job["payload"]["source_id"]) == account_id for job in jobs)


async def test_poll_noop_when_no_change() -> None:
    account_id, _ = await _seed_synced_account(history_id=10)

    async with engine.begin() as connection:
        result = await service.poll_history(connection, connected_account_id=account_id)

    assert result == {"noop": True}

    async with engine.connect() as connection:
        cursor = (
            await connection.execute(
                select(gmail_sync_cursors).where(
                    gmail_sync_cursors.c.connected_account_id == account_id
                )
            )
        ).mappings().first()
    assert cursor["last_successful_sync_at"] is not None
