import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import insert

from app.core.config import settings
from app.core.database import engine
from app.domains.assistant_decisions import fake_llm as fake_llm_module
from app.domains.assistant_decisions import llm as llm_module
from app.domains.identity.models import users, workspaces
from app.domains.labels.models import label_correction_signals, service_labels
from app.domains.mail_intake.models import gmail_message_labels, gmail_messages, message_excerpts
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings


@pytest.fixture(autouse=True)
def _test_token_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-jwt-secret-at-least-32-bytes-long")


@pytest.fixture(autouse=True)
def _fresh_fake_llm():
    """test마다 fresh FakeAssistantLLM을 써서 fail_next_* state 오염을 피한다."""
    fake = fake_llm_module.FakeAssistantLLM()
    llm_module.set_llm(fake)
    yield fake
    llm_module.set_llm(None)


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


async def seed_source_settings(
    connected_account_id: uuid.UUID, *, summary_enabled: bool = True
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_source_settings).values(
                id=uuid.uuid4(),
                connected_account_id=connected_account_id,
                briefing_enabled=True,
                summary_enabled=summary_enabled,
                notification_enabled=True,
                paused=False,
                updated_at=datetime.now(timezone.utc),
            )
        )


async def seed_scope(
    *, status: str = "connected", summary_enabled: bool = True
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """(workspace_id, user_id, connected_account_id)를 반환한다."""
    workspace_id, user_id = await seed_workspace_and_user()
    account_id = await seed_connected_account(workspace_id, status=status)
    await seed_source_settings(account_id, summary_enabled=summary_enabled)
    return workspace_id, user_id, account_id


async def seed_message(
    connected_account_id: uuid.UUID,
    *,
    subject: str | None = "분기 보고서 공유드립니다",
    sender: str | None = "manager@example.com",
    snippet: str | None = "이번 분기 실적 요약을 첨부드립니다.",
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
                subject=subject,
                sender=sender,
                snippet=snippet,
                is_read=is_read,
                is_archived=is_archived,
            )
        )
    return message_id


async def seed_message_labels(message_id: uuid.UUID, label_names: list[str]) -> None:
    async with engine.begin() as connection:
        for name in label_names:
            await connection.execute(
                insert(gmail_message_labels).values(
                    id=uuid.uuid4(),
                    message_id=message_id,
                    gmail_label_id=name,
                    label_name=name,
                )
            )


async def seed_message_excerpt(message_id: uuid.UUID, excerpt_text: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(message_excerpts).values(
                id=uuid.uuid4(),
                message_id=message_id,
                excerpt_text=excerpt_text,
                updated_at=datetime.now(timezone.utc),
            )
        )


async def seed_service_label(workspace_id: uuid.UUID, *, name: str = "업무") -> uuid.UUID:
    label_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(service_labels).values(
                id=label_id,
                workspace_id=workspace_id,
                name=name,
                order_index=0,
                hidden=False,
                updated_at=datetime.now(timezone.utc),
            )
        )
    return label_id


async def seed_correction_signal(
    *, message_id: uuid.UUID, service_label_id: uuid.UUID, actor_id: uuid.UUID
) -> uuid.UUID:
    signal_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(label_correction_signals).values(
                id=signal_id,
                message_id=message_id,
                service_label_id=service_label_id,
                actor_id=actor_id,
            )
        )
    return signal_id
