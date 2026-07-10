import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import insert

from app.core.config import settings
from app.core.database import engine
from app.domains.identity.models import users, workspaces
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings


@pytest.fixture(autouse=True)
def _test_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-at-least-32-bytes-long")


async def seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


async def seed_user() -> uuid.UUID:
    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(users).values(
                id=user_id,
                google_subject=str(uuid.uuid4()),
                email=f"{uuid.uuid4()}@example.com",
                display_name=None,
                last_login_at=None,
            )
        )
    return user_id


async def seed_connected_account(
    workspace_id: uuid.UUID, *, status: str = "connected", notification_enabled: bool = True
) -> uuid.UUID:
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
        await connection.execute(
            insert(gmail_source_settings).values(
                id=uuid.uuid4(),
                connected_account_id=account_id,
                briefing_enabled=True,
                summary_enabled=True,
                notification_enabled=notification_enabled,
                paused=False,
                updated_at=datetime.now(timezone.utc),
            )
        )
    return account_id


async def seed_scope(*, notification_enabled: bool = True) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """workspace + user + connected account(settings row 포함)를 반환한다."""
    workspace_id = await seed_workspace()
    user_id = await seed_user()
    account_id = await seed_connected_account(
        workspace_id, notification_enabled=notification_enabled
    )
    return workspace_id, user_id, account_id
