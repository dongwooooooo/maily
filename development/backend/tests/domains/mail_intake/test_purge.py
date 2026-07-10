import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select

from app.core.database import engine
from app.domains.mail_intake.models import gmail_message_labels, gmail_messages, message_excerpts
from app.domains.mail_intake.purge import purge_source
from tests.domains.mail_intake.conftest import seed_connected_account, seed_message


async def test_purge_deletes_messages_excerpts_and_labels() -> None:
    account_id = await seed_connected_account()
    message_id = await seed_message(account_id)

    async with engine.begin() as connection:
        await connection.execute(
            insert(message_excerpts).values(
                id=uuid.uuid4(),
                message_id=message_id,
                excerpt_text="short preview",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await connection.execute(
            insert(gmail_message_labels).values(
                id=uuid.uuid4(), message_id=message_id, gmail_label_id="INBOX", label_name="INBOX"
            )
        )

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        messages = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().all()
        excerpts = (
            await connection.execute(select(message_excerpts).where(message_excerpts.c.message_id == message_id))
        ).mappings().all()
        labels = (
            await connection.execute(
                select(gmail_message_labels).where(gmail_message_labels.c.message_id == message_id)
            )
        ).mappings().all()

    assert messages == []
    assert excerpts == []
    assert labels == []


async def test_purge_no_messages_is_noop() -> None:
    account_id = await seed_connected_account()
    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)
    # No exception — that's the assertion.


async def test_purge_only_affects_target_account() -> None:
    account_id = await seed_connected_account()
    other_account_id = await seed_connected_account()
    message_id = await seed_message(account_id)
    other_message_id = await seed_message(other_account_id)

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        remaining = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == other_message_id))
        ).mappings().all()
        purged = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().all()

    assert len(remaining) == 1
    assert purged == []
