import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert

from app.core.database import engine
from app.domains.identity.models import workspaces
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_messages
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings


@pytest.fixture(autouse=True)
def _reset_active_reader():
    """gmail_reader.get_reader()는 module-level singleton으로 fallback한다.
    한 test에서 seed한 FakeGmailReader가 다음 test로 새지 않도록 test 사이에 reset한다."""
    yield
    set_reader(None)


async def seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


async def seed_connected_account(
    *,
    workspace_id: uuid.UUID | None = None,
    status: str = "connected",
    paused: bool = False,
    gmail_address: str | None = None,
) -> uuid.UUID:
    if workspace_id is None:
        workspace_id = await seed_workspace()
    account_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with engine.begin() as connection:
        await connection.execute(
            insert(connected_gmail_accounts).values(
                id=account_id,
                workspace_id=workspace_id,
                gmail_address=gmail_address or f"user-{uuid.uuid4()}@gmail.com",
                display_name=None,
                status=status,
                version=0,
                connected_at=now,
            )
        )
        await connection.execute(
            insert(gmail_source_settings).values(
                id=uuid.uuid4(),
                connected_account_id=account_id,
                paused=paused,
                updated_at=now,
            )
        )
    return account_id


async def seed_message(
    connected_account_id: uuid.UUID,
    *,
    is_read: bool = False,
    is_archived: bool = False,
) -> uuid.UUID:
    message_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=connected_account_id,
                gmail_message_id=f"gmail-{uuid.uuid4()}",
                gmail_thread_id=f"thread-{uuid.uuid4()}",
                is_read=is_read,
                is_archived=is_archived,
                last_history_id=1,
            )
        )
    return message_id
