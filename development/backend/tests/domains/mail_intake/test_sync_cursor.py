from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import engine
from app.domains.mail_intake import repository, service
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_sync_cursors, gmail_watch_registrations
from tests.domains.mail_intake.conftest import seed_connected_account


async def test_register_watch_sets_expiration() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(account_id, messages=[], history_id=1)
    set_reader(reader)

    async with engine.begin() as connection:
        result = await service.register_watch(connection, connected_account_id=account_id)

    async with engine.connect() as connection:
        registration = (
            await connection.execute(
                select(gmail_watch_registrations).where(
                    gmail_watch_registrations.c.connected_account_id == account_id
                )
            )
        ).mappings().first()
        cursor = (
            await connection.execute(
                select(gmail_sync_cursors).where(
                    gmail_sync_cursors.c.connected_account_id == account_id
                )
            )
        ).mappings().first()

    assert registration is not None
    assert registration["status"] == "active"
    assert registration["expiration"] == result["expiration"]
    assert cursor is not None
    assert cursor["watch_expiration_at"] == result["expiration"]


async def test_cursor_advances_on_success() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(
        account_id,
        messages=[FakeMessage(gmail_message_id="msg-1", gmail_thread_id="thread-1")],
        history_id=10,
    )
    set_reader(reader)
    async with engine.begin() as connection:
        await service.sync_full(connection, connected_account_id=account_id, reason="initial")

    reader.push_history(
        account_id,
        record_type="message_added",
        message=FakeMessage(gmail_message_id="msg-2", gmail_thread_id="thread-2"),
    )

    async with engine.begin() as connection:
        await service.sync_delta(
            connection, connected_account_id=account_id, start_history_id=10, trigger="poll"
        )

    async with engine.connect() as connection:
        cursor = (
            await connection.execute(
                select(gmail_sync_cursors).where(
                    gmail_sync_cursors.c.connected_account_id == account_id
                )
            )
        ).mappings().first()

    assert cursor["last_history_id"] == 11
    assert cursor["cursor_status"] == "valid"


async def test_last_successful_sync_at_updates() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(account_id, messages=[], history_id=1)
    set_reader(reader)

    async with engine.begin() as connection:
        await service.sync_full(connection, connected_account_id=account_id, reason="initial")

    async with engine.connect() as connection:
        cursor = (
            await connection.execute(
                select(gmail_sync_cursors).where(
                    gmail_sync_cursors.c.connected_account_id == account_id
                )
            )
        ).mappings().first()

    assert cursor["last_successful_sync_at"] is not None


async def test_renew_selects_expiring_watches() -> None:
    soon_account = await seed_connected_account()
    far_account = await seed_connected_account()
    now = datetime.now(timezone.utc)

    async with engine.begin() as connection:
        await repository.insert_watch_registration(
            connection,
            connected_account_id=soon_account,
            topic_name="projects/maily-fake/topics/gmail-fake",
            expiration=now + timedelta(hours=2),
            status="active",
        )
        await repository.insert_watch_registration(
            connection,
            connected_account_id=far_account,
            topic_name="projects/maily-fake/topics/gmail-fake",
            expiration=now + timedelta(days=6),
            status="active",
        )

    async with engine.connect() as connection:
        expiring = await repository.list_watches_expiring_before(
            connection, before=now + timedelta(hours=24)
        )

    expiring_account_ids = {row["connected_account_id"] for row in expiring}
    assert soon_account in expiring_account_ids
    assert far_account not in expiring_account_ids
