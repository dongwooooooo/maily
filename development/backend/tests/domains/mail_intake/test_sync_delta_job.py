from sqlalchemy import select

from app.core.database import engine
from app.domains.mail_intake import repository, service
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_messages, gmail_sync_cursors
from tests.domains.mail_intake.conftest import seed_connected_account


async def test_delta_applies_history_records() -> None:
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
        message=FakeMessage(
            gmail_message_id="msg-2", gmail_thread_id="thread-2", subject="New mail"
        ),
    )

    async with engine.begin() as connection:
        result = await service.sync_delta(
            connection, connected_account_id=account_id, start_history_id=10, trigger="notification"
        )

    assert len(result["message_ids"]) == 1
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(gmail_messages).where(
                    gmail_messages.c.connected_account_id == account_id,
                    gmail_messages.c.gmail_message_id == "msg-2",
                )
            )
        ).mappings().first()
    assert row is not None
    assert row["subject"] == "New mail"


async def test_delta_idempotent_on_replay() -> None:
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
        first = await service.sync_delta(
            connection, connected_account_id=account_id, start_history_id=10, trigger="notification"
        )
    # Replay: cursor가 이미 지나간 뒤 같은 notification(같은 start_history_id)이
    # 다시 도착한다.
    async with engine.begin() as connection:
        second = await service.sync_delta(
            connection, connected_account_id=account_id, start_history_id=10, trigger="notification"
        )

    assert first["message_ids"] != []
    assert second.get("noop") is True
    assert second.get("message_ids", []) == []

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().all()
    assert len(rows) == 2  # msg-1(full) + msg-2(delta) — replay로 중복되지 않음


async def test_invalid_cursor_schedules_full() -> None:
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
    async with engine.begin() as connection:
        await repository.mark_cursor_invalid(connection, connected_account_id=account_id)

    async with engine.begin() as connection:
        result = await service.sync_delta(
            connection, connected_account_id=account_id, start_history_id=10, trigger="notification"
        )

    assert result["promoted_to_full"] is True
    async with engine.connect() as connection:
        cursor = (
            await connection.execute(
                select(gmail_sync_cursors).where(
                    gmail_sync_cursors.c.connected_account_id == account_id
                )
            )
        ).mappings().first()
    assert cursor["cursor_status"] == "valid"
