import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select

from app.core.database import engine
from app.core.errors import NotFoundError
from app.core.outbox import outbox_events
from app.domains.identity.models import workspaces
from app.domains.mail_sources.models import gmail_oauth_credentials
from app.domains.mail_sources.repository import get_connected_account
from app.domains.mail_sources.schemas import ConnectGmailSourceInput, DisconnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source, disconnect_gmail_source

import pytest


async def _seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


async def _seed_source(**overrides):
    data = {
        "workspace_id": await _seed_workspace(),
        "gmail_address": f"user-{uuid.uuid4()}@gmail.com",
        "access_token": "ya29.a0-example-access-token",
        "refresh_token": "1//0g-example-refresh-token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    data.update(overrides)
    async with engine.begin() as connection:
        source, _ = await connect_gmail_source(connection, ConnectGmailSourceInput(**data))
    return source


async def test_disconnect_marks_disconnecting_and_revokes_credential() -> None:
    source = await _seed_source()

    async with engine.begin() as connection:
        result = await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=source.workspace_id, connected_account_id=source.id),
        )

    assert result.status == "disconnecting"

    async with engine.connect() as connection:
        account = await get_connected_account(connection, connected_account_id=source.id)
        credential = (
            await connection.execute(
                select(gmail_oauth_credentials).where(
                    gmail_oauth_credentials.c.connected_account_id == source.id
                )
            )
        ).mappings().first()

    assert account["status"] == "disconnecting"
    assert account["disconnected_at"] is not None
    assert credential["revoked_at"] is not None


async def test_disconnect_emits_gmail_source_disconnected() -> None:
    source = await _seed_source()

    async with engine.begin() as connection:
        await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=source.workspace_id, connected_account_id=source.id),
        )

    key = f"source:{source.id}:disconnected:1"
    async with engine.connect() as connection:
        row = (
            await connection.execute(select(outbox_events).where(outbox_events.c.idempotency_key == key))
        ).mappings().first()

    assert row is not None
    assert row["event_type"] == "gmail_source_disconnected"
    assert row["payload"]["source_id"] == str(source.id)
    assert row["payload"]["workspace_id"] == str(source.workspace_id)


async def test_disconnect_idempotent_on_already_disconnecting() -> None:
    """[멱등] 재요청은 두 번째 event를 발행하지 않는다."""
    source = await _seed_source()

    async with engine.begin() as connection:
        first = await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=source.workspace_id, connected_account_id=source.id),
        )
    async with engine.begin() as connection:
        second = await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=source.workspace_id, connected_account_id=source.id),
        )

    assert first.status == second.status == "disconnecting"

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "gmail_source_disconnected")
            )
        ).mappings().all()
    matching = [r for r in rows if r["payload"]["source_id"] == str(source.id)]
    assert len(matching) == 1


async def test_disconnect_unknown_source_404() -> None:
    workspace_id = await _seed_workspace()
    with pytest.raises(NotFoundError):
        async with engine.begin() as connection:
            await disconnect_gmail_source(
                connection,
                DisconnectGmailSourceInput(workspace_id=workspace_id, connected_account_id=uuid.uuid4()),
            )
