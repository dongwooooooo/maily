import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select

from app.core.database import engine
from app.domains.identity.models import workspaces
from app.domains.mail_sources.models import gmail_oauth_credentials
from app.domains.mail_sources.purge import purge_source
from app.domains.mail_sources.repository import get_connected_account
from app.domains.mail_sources.schemas import ConnectGmailSourceInput, DisconnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source, disconnect_gmail_source


async def _seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


async def _seed_disconnecting_source():
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
        source, _ = await connect_gmail_source(connection, data)
    async with engine.begin() as connection:
        await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=workspace_id, connected_account_id=source.id),
        )
    return source


async def test_purge_deletes_credential_and_marks_disconnected() -> None:
    source = await _seed_disconnecting_source()

    async with engine.begin() as connection:
        await purge_source(connection, source_id=source.id)

    async with engine.connect() as connection:
        account = await get_connected_account(connection, connected_account_id=source.id)
        credential = (
            await connection.execute(
                select(gmail_oauth_credentials).where(
                    gmail_oauth_credentials.c.connected_account_id == source.id
                )
            )
        ).mappings().first()

    assert account["status"] == "disconnected"
    assert credential is None


async def test_purge_unknown_source_is_noop() -> None:
    async with engine.begin() as connection:
        await purge_source(connection, source_id=uuid.uuid4())
    # No exception — that's the assertion.
