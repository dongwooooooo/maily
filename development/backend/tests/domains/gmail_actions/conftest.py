import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import insert

from app.core.config import settings
from app.core.database import engine
from app.domains.identity.models import users, workspaces
from app.domains.mail_intake.models import gmail_messages
from app.domains.mail_sources.models import connected_gmail_accounts


@pytest.fixture(autouse=True)
def _test_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-at-least-32-bytes-long")


async def seed_workspace_and_user() -> tuple[uuid.UUID, uuid.UUID]:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
        await connection.execute(
            insert(users).values(
                id=user_id,
                google_subject=str(uuid.uuid4()),
                email=f"{uuid.uuid4()}@example.com",
                display_name=None,
            )
        )
    return workspace_id, user_id


async def seed_connected_account(workspace_id: uuid.UUID, *, status: str = "connected") -> uuid.UUID:
    account_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(connected_gmail_accounts).values(
                id=account_id,
                workspace_id=workspace_id,
                gmail_address=f"user-{uuid.uuid4()}@gmail.com",
                display_name=None,
                status=status,
                version=0,
                connected_at=datetime.now(timezone.utc),
            )
        )
    return account_id


async def seed_scope(*, status: str = "connected") -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (workspace_id, user_id, connected_account_id)."""
    workspace_id, user_id = await seed_workspace_and_user()
    account_id = await seed_connected_account(workspace_id, status=status)
    return workspace_id, user_id, account_id


async def seed_message(connected_account_id: uuid.UUID) -> uuid.UUID:
    message_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=connected_account_id,
                gmail_message_id=f"gmail-{uuid.uuid4()}",
                gmail_thread_id=f"thread-{uuid.uuid4()}",
            )
        )
    return message_id
