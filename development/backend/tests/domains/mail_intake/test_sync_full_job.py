from sqlalchemy import select

from app.core.database import engine
from app.domains.mail_intake import service
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_messages, gmail_sync_cursors, sync_runs
from tests.domains.mail_intake.conftest import seed_connected_account


async def test_full_resync_is_idempotent() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(
        account_id,
        messages=[
            FakeMessage(gmail_message_id="msg-1", gmail_thread_id="thread-1", subject="First"),
            FakeMessage(gmail_message_id="msg-2", gmail_thread_id="thread-2", subject="Second"),
        ],
        history_id=20,
    )
    set_reader(reader)

    async with engine.begin() as connection:
        first_result = await service.sync_full(
            connection, connected_account_id=account_id, reason="initial"
        )
    async with engine.begin() as connection:
        second_result = await service.sync_full(
            connection, connected_account_id=account_id, reason="manual"
        )

    assert len(first_result["message_ids"]) == 2
    assert second_result["message_ids"] == []

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().all()
        sync_run_rows = (
            await connection.execute(
                select(sync_runs).where(sync_runs.c.connected_account_id == account_id)
            )
        ).mappings().all()

    assert len(rows) == 2  # 두 번째 run으로 중복되지 않음
    assert len(sync_run_rows) == 2  # no-op run까지 각각 기록됨
    assert all(r["status"] == "succeeded" for r in sync_run_rows)


async def test_invalid_cursor_triggers_full() -> None:
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

    # Gmail이 history window를 완전히 잊은 상황을 흉내낸다. 다음 delta attempt는
    # pre-set cursor flag가 아니라 mid-flight에서 이를 감지하고 full로 fallback해야 한다.
    reader.expire_history_before(account_id, 999)
    reader.push_history(
        account_id,
        record_type="message_added",
        message=FakeMessage(gmail_message_id="msg-2", gmail_thread_id="thread-2"),
    )

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
        rows = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().all()

    assert cursor["cursor_status"] == "valid"
    # Full resync는 list_message_ids에서 snapshot을 다시 파생한다. 이미 알고 있던 message와
    # history 만료 후 추가된 message가 모두 포함된다.
    assert {r["gmail_message_id"] for r in rows} == {"msg-1", "msg-2"}
