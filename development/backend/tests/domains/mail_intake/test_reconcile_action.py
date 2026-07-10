from sqlalchemy import select

from app.core.database import engine
from app.domains.mail_intake import service
from app.domains.mail_intake.jobs.reconcile_action import handle
from app.domains.mail_intake.models import gmail_message_labels, gmail_messages
from tests.domains.mail_intake.conftest import seed_connected_account, seed_message


async def test_removing_unread_marks_read() -> None:
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id, is_read=False)

    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection, message_id=message_id, add_label_ids=[], remove_label_ids=["UNREAD"]
        )

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
    assert row["is_read"] is True


async def test_removing_inbox_marks_archived() -> None:
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id, is_archived=False)

    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection, message_id=message_id, add_label_ids=[], remove_label_ids=["INBOX"]
        )

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
    assert row["is_archived"] is True


async def test_adding_unread_marks_unread() -> None:
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id, is_read=True)

    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection, message_id=message_id, add_label_ids=["UNREAD"], remove_label_ids=[]
        )

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
    assert row["is_read"] is False


async def test_label_apply_action_updates_message_labels() -> None:
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id)

    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection, message_id=message_id, add_label_ids=["Label_5"], remove_label_ids=[]
        )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_message_labels).where(gmail_message_labels.c.message_id == message_id)
            )
        ).mappings().all()
    assert {r["gmail_label_id"] for r in rows} == {"Label_5"}


async def test_message_not_in_snapshot_is_noop() -> None:
    """[선행조건] purge된/한 번도 sync 안 된 message_id -> 조용히 무시."""
    import uuid as uuid_module

    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection,
            message_id=uuid_module.uuid4(),
            add_label_ids=["UNREAD"],
            remove_label_ids=[],
        )
    # exception이 없는 것이 assertion이다.


async def test_last_history_id_untouched() -> None:
    """own-action reconcile은 sync tick이 아니다. cursor field는 마지막 실제 sync가
    남긴 값 그대로 유지된다."""
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id)

    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection, message_id=message_id, add_label_ids=[], remove_label_ids=["UNREAD"]
        )

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
    assert row["last_history_id"] == 1


async def test_job_handler_reads_payload_shape() -> None:
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id)

    await handle(
        {
            "message_id": str(message_id),
            "add_label_ids": [],
            "remove_label_ids": ["UNREAD"],
        }
    )

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
    assert row["is_read"] is True
