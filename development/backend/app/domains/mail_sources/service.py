import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import crypto
from app.core.outbox import append_event
from app.domains.mail_sources import repository
from app.domains.mail_sources.schemas import ConnectGmailSourceInput, ConnectedSource


def _to_schema(row: dict) -> ConnectedSource:
    return ConnectedSource(
        id=row["id"],
        workspace_id=row["workspace_id"],
        gmail_address=row["gmail_address"],
        display_name=row["display_name"],
        status=row["status"],
        connected_at=row["connected_at"],
    )


async def connect_gmail_source(
    connection: AsyncConnection, data: ConnectGmailSourceInput
) -> tuple[ConnectedSource, bool]:
    """Connect a Gmail address to a workspace.

    Idempotent on (workspace_id, gmail_address) among active
    (non-disconnected) connections: a sequential duplicate request is
    caught by the pre-check below, a genuinely concurrent one is
    caught by the partial unique index and falls back to the same
    re-query — either way the caller gets the existing source back
    with is_new=False instead of a second row or a second
    gmail_source_connected event.
    """
    existing = await repository.find_active_source_by_address(
        connection, workspace_id=data.workspace_id, gmail_address=data.gmail_address
    )
    if existing is not None:
        return _to_schema(existing), False

    account_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    try:
        async with connection.begin_nested():
            await repository.insert_connected_account(
                connection,
                account_id=account_id,
                workspace_id=data.workspace_id,
                gmail_address=data.gmail_address,
                status="connected",
                connected_at=now,
            )
    except IntegrityError:
        existing = await repository.find_active_source_by_address(
            connection, workspace_id=data.workspace_id, gmail_address=data.gmail_address
        )
        if existing is None:
            raise
        return _to_schema(existing), False

    await repository.insert_credential(
        connection,
        credential_id=uuid.uuid4(),
        connected_account_id=account_id,
        access_token_ciphertext=crypto.encrypt_token(data.access_token),
        refresh_token_ciphertext=crypto.encrypt_token(data.refresh_token),
        encryption_key_version=crypto.CURRENT_KEY_VERSION,
        scope=data.scope,
        expires_at=data.expires_at,
    )
    await repository.insert_default_settings(
        connection, settings_id=uuid.uuid4(), connected_account_id=account_id, updated_at=now
    )
    await append_event(
        connection,
        event_type="gmail_source_connected",
        producer_domain="mail_sources",
        payload={"source_id": str(account_id), "workspace_id": str(data.workspace_id)},
        idempotency_key=f"source:{account_id}:connected:0",
    )

    return (
        ConnectedSource(
            id=account_id,
            workspace_id=data.workspace_id,
            gmail_address=data.gmail_address,
            display_name=None,
            status="connected",
            connected_at=now,
        ),
        True,
    )
