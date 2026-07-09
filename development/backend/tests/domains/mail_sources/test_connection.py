import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, update

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.identity.models import workspaces
from app.domains.mail_sources.models import connected_gmail_accounts
from app.domains.mail_sources.schemas import ConnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source


async def _seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


async def _input(**overrides) -> ConnectGmailSourceInput:
    defaults = {
        "workspace_id": await _seed_workspace(),
        "gmail_address": f"user-{uuid.uuid4()}@gmail.com",
        "access_token": "ya29.a0-example-access-token",
        "refresh_token": "1//0g-example-refresh-token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    defaults.update(overrides)
    return ConnectGmailSourceInput(**defaults)


async def test_connect_creates_source_with_connected_status() -> None:
    data = await _input()

    async with engine.begin() as connection:
        source, is_new = await connect_gmail_source(connection, data)

    assert is_new is True
    assert source.gmail_address == data.gmail_address
    assert source.status == "connected"
    assert source.display_name is None


async def test_connect_appends_gmail_source_connected_event() -> None:
    data = await _input()

    async with engine.begin() as connection:
        source, _ = await connect_gmail_source(connection, data)

    key = f"source:{source.id}:connected:0"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()

    assert row is not None
    assert row["event_type"] == "gmail_source_connected"
    assert row["producer_domain"] == "mail_sources"
    assert row["payload"]["source_id"] == str(source.id)


async def test_duplicate_active_address_returns_existing_source_without_new_event() -> None:
    data = await _input()

    async with engine.begin() as connection:
        first, first_is_new = await connect_gmail_source(connection, data)
    async with engine.begin() as connection:
        second, second_is_new = await connect_gmail_source(connection, data)

    assert first_is_new is True
    assert second_is_new is False
    assert second.id == first.id

    key = f"source:{first.id}:connected:0"
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).all()
    assert len(rows) == 1


async def test_disconnected_address_is_reconnectable_as_new_row() -> None:
    data = await _input()

    async with engine.begin() as connection:
        first, _ = await connect_gmail_source(connection, data)

    async with engine.begin() as connection:
        await connection.execute(
            update(connected_gmail_accounts)
            .where(connected_gmail_accounts.c.id == first.id)
            .values(status="disconnected")
        )

    async with engine.begin() as connection:
        second, second_is_new = await connect_gmail_source(connection, data)

    assert second_is_new is True
    assert second.id != first.id


async def test_concurrent_connect_same_address_creates_only_one_active_source() -> None:
    data = await _input()

    async def attempt():
        async with engine.begin() as connection:
            return await connect_gmail_source(connection, data)

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(is_new for _, is_new in results) == [False, True]
    assert results[0][0].id == results[1][0].id
