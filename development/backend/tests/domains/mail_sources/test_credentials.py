import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from app.core import crypto
from app.core.config import settings
from app.core.database import engine
from app.domains.identity.models import workspaces
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_oauth_credentials
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


async def test_token_plaintext_never_persisted() -> None:
    data = await _input()

    async with engine.begin() as connection:
        source, _ = await connect_gmail_source(connection, data)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(gmail_oauth_credentials).where(
                    gmail_oauth_credentials.c.connected_account_id == source.id
                )
            )
        ).mappings().first()

    assert data.access_token.encode() not in row["access_token_ciphertext"]
    assert data.refresh_token.encode() not in row["refresh_token_ciphertext"]
    assert row["encryption_key_version"] == crypto.CURRENT_KEY_VERSION
    assert crypto.decrypt_token(row["access_token_ciphertext"]) == data.access_token
    assert crypto.decrypt_token(row["refresh_token_ciphertext"]) == data.refresh_token


async def test_missing_encryption_key_rolls_back_entire_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "token_encryption_key", "")
    data = await _input()

    with pytest.raises(crypto.MissingTokenEncryptionKeyError):
        async with engine.begin() as connection:
            await connect_gmail_source(connection, data)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(connected_gmail_accounts).where(
                    connected_gmail_accounts.c.gmail_address == data.gmail_address
                )
            )
        ).mappings().first()

    assert row is None
