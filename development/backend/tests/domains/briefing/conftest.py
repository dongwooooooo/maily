import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert

from app.core.config import settings
from app.core.database import engine
from app.domains.identity.models import users, workspaces
from app.domains.mail_intake.models import gmail_messages, message_excerpts
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings


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


async def seed_connected_account(
    workspace_id: uuid.UUID,
    *,
    status: str = "connected",
    gmail_address: str | None = None,
    briefing_enabled: bool = True,
) -> uuid.UUID:
    account_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(connected_gmail_accounts).values(
                id=account_id,
                workspace_id=workspace_id,
                gmail_address=gmail_address or f"user-{uuid.uuid4()}@gmail.com",
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
                briefing_enabled=briefing_enabled,
                summary_enabled=True,
                notification_enabled=True,
                paused=False,
                updated_at=datetime.now(timezone.utc),
            )
        )
    return account_id


async def seed_scope(
    *, status: str = "connected", briefing_enabled: bool = True
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (workspace_id, user_id, connected_account_id)."""
    workspace_id, user_id = await seed_workspace_and_user()
    account_id = await seed_connected_account(
        workspace_id, status=status, briefing_enabled=briefing_enabled
    )
    return workspace_id, user_id, account_id


async def seed_message(
    connected_account_id: uuid.UUID,
    *,
    subject: str = "Q3 정산 안내",
    sender: str = "billing@example.com",
    snippet: str = "이번 분기 정산 내역을 안내드립니다.",
    received_at: datetime | None = None,
    is_read: bool = False,
    is_archived: bool = False,
    excerpt_text: str | None = "이번 분기 정산 내역을 첨부와 같이 안내드립니다.",
) -> uuid.UUID:
    message_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=connected_account_id,
                gmail_message_id=f"gmail-{uuid.uuid4()}",
                gmail_thread_id=f"thread-{uuid.uuid4()}",
                subject=subject,
                sender=sender,
                snippet=snippet,
                received_at=received_at or datetime.now(timezone.utc),
                is_read=is_read,
                is_archived=is_archived,
            )
        )
        if excerpt_text is not None:
            await connection.execute(
                insert(message_excerpts).values(
                    id=uuid.uuid4(),
                    message_id=message_id,
                    excerpt_text=excerpt_text,
                    updated_at=datetime.now(timezone.utc),
                )
            )
    return message_id
