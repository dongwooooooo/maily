import uuid
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.mail_sources.models import (
    connected_gmail_accounts,
    gmail_oauth_credentials,
    gmail_source_settings,
)


async def find_active_source_by_address(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, gmail_address: str
) -> dict | None:
    row = (
        await connection.execute(
            select(connected_gmail_accounts).where(
                connected_gmail_accounts.c.workspace_id == workspace_id,
                connected_gmail_accounts.c.gmail_address == gmail_address,
                connected_gmail_accounts.c.status != "disconnected",
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def insert_connected_account(
    connection: AsyncConnection,
    *,
    account_id: uuid.UUID,
    workspace_id: uuid.UUID,
    gmail_address: str,
    status: str,
    connected_at: datetime,
) -> None:
    await connection.execute(
        insert(connected_gmail_accounts).values(
            id=account_id,
            workspace_id=workspace_id,
            gmail_address=gmail_address,
            display_name=None,
            status=status,
            version=0,
            connected_at=connected_at,
        )
    )


async def insert_credential(
    connection: AsyncConnection,
    *,
    credential_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    access_token_ciphertext: bytes,
    refresh_token_ciphertext: bytes,
    encryption_key_version: int,
    scope: str,
    expires_at: datetime,
) -> None:
    await connection.execute(
        insert(gmail_oauth_credentials).values(
            id=credential_id,
            connected_account_id=connected_account_id,
            access_token_ciphertext=access_token_ciphertext,
            refresh_token_ciphertext=refresh_token_ciphertext,
            encryption_key_version=encryption_key_version,
            scope=scope,
            expires_at=expires_at,
        )
    )


async def insert_default_settings(
    connection: AsyncConnection,
    *,
    settings_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    updated_at: datetime,
) -> None:
    await connection.execute(
        insert(gmail_source_settings).values(
            id=settings_id,
            connected_account_id=connected_account_id,
            updated_at=updated_at,
        )
    )


async def get_credential(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_oauth_credentials).where(
                gmail_oauth_credentials.c.connected_account_id == connected_account_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None
