import uuid
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.gmail_actions.models import (
    activity_logs,
    gmail_action_commands,
    undo_actions,
)
from app.domains.mail_sources.models import connected_gmail_accounts

# NOTE: this reads connected_gmail_accounts (workspace_id/status scoping
# columns only — never the encrypted OAuth credential table) to resolve a
# command's workspace and to gate requests against disconnecting/disconnected
# accounts, per gmail_actions.md "workspace 스코프는
# command_id→connected_account_id→workspace로 제한". This is not the OAuth
# token boundary the negative tests enforce (see test_mutation_port_boundary.py).


async def get_connected_account_scope(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(
                connected_gmail_accounts.c.id,
                connected_gmail_accounts.c.workspace_id,
                connected_gmail_accounts.c.status,
            ).where(connected_gmail_accounts.c.id == connected_account_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


# ---- gmail_action_commands ----------------------------------------------


async def insert_command(
    connection: AsyncConnection,
    *,
    command_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    message_id: uuid.UUID | None,
    action_type: str,
    payload: dict,
    idempotency_key: str,
    requested_by: uuid.UUID,
    requested_at: datetime,
) -> None:
    await connection.execute(
        insert(gmail_action_commands).values(
            id=command_id,
            connected_account_id=connected_account_id,
            message_id=message_id,
            action_type=action_type,
            payload=payload,
            idempotency_key=idempotency_key,
            status="pending",
            version=0,
            changed=None,
            requested_by=requested_by,
            requested_at=requested_at,
        )
    )


async def get_command_by_idempotency_key(
    connection: AsyncConnection, *, idempotency_key: str
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_action_commands).where(
                gmail_action_commands.c.idempotency_key == idempotency_key
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_command(connection: AsyncConnection, *, command_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_action_commands).where(gmail_action_commands.c.id == command_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def lock_command_for_update(
    connection: AsyncConnection, *, command_id: uuid.UUID
) -> dict | None:
    """SELECT ... FOR UPDATE — used by execute_action to read-then-transition safely."""
    row = (
        await connection.execute(
            select(gmail_action_commands)
            .where(gmail_action_commands.c.id == command_id)
            .with_for_update()
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def mark_command_applied(
    connection: AsyncConnection,
    *,
    command_id: uuid.UUID,
    version: int,
    changed: bool,
    applied_at: datetime,
) -> None:
    await connection.execute(
        update(gmail_action_commands)
        .where(gmail_action_commands.c.id == command_id)
        .values(status="applied", version=version, changed=changed, applied_at=applied_at)
    )


async def mark_command_failed(
    connection: AsyncConnection,
    *,
    command_id: uuid.UUID,
    version: int,
    error_reason: str,
    failed_at: datetime,
) -> None:
    await connection.execute(
        update(gmail_action_commands)
        .where(gmail_action_commands.c.id == command_id)
        .values(status="failed", version=version, error_reason=error_reason, failed_at=failed_at)
    )


async def mark_command_compensating(
    connection: AsyncConnection, *, command_id: uuid.UUID, version: int
) -> None:
    await connection.execute(
        update(gmail_action_commands)
        .where(gmail_action_commands.c.id == command_id)
        .values(status="compensating", version=version)
    )


async def mark_command_undone(
    connection: AsyncConnection, *, command_id: uuid.UUID, version: int
) -> None:
    await connection.execute(
        update(gmail_action_commands)
        .where(gmail_action_commands.c.id == command_id)
        .values(status="undone", version=version)
    )


# ---- activity_logs --------------------------------------------------------


async def insert_activity_log(
    connection: AsyncConnection,
    *,
    activity_id: uuid.UUID,
    workspace_id: uuid.UUID,
    command_id: uuid.UUID | None,
    action_summary: str,
    actor_id: uuid.UUID | None,
    occurred_at: datetime,
) -> None:
    await connection.execute(
        insert(activity_logs).values(
            id=activity_id,
            workspace_id=workspace_id,
            command_id=command_id,
            action_summary=action_summary,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )
    )


async def get_activity_log_by_command(
    connection: AsyncConnection, *, command_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(activity_logs).where(activity_logs.c.command_id == command_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_activity_log(
    connection: AsyncConnection, *, activity_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(activity_logs).where(activity_logs.c.id == activity_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_activity_logs(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[dict]:
    rows = (
        await connection.execute(
            select(activity_logs)
            .where(activity_logs.c.workspace_id == workspace_id)
            .order_by(activity_logs.c.occurred_at.desc())
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# ---- undo_actions ----------------------------------------------------------


async def insert_undo_action(
    connection: AsyncConnection,
    *,
    undo_id: uuid.UUID,
    activity_id: uuid.UUID,
    original_command_id: uuid.UUID,
    undo_available: bool,
) -> None:
    await connection.execute(
        insert(undo_actions).values(
            id=undo_id,
            activity_id=activity_id,
            original_command_id=original_command_id,
            reverse_command_id=None,
            undo_available=undo_available,
            undone_at=None,
        )
    )


async def get_undo_action_by_activity(
    connection: AsyncConnection, *, activity_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(undo_actions).where(undo_actions.c.activity_id == activity_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_undo_action_by_reverse_command(
    connection: AsyncConnection, *, reverse_command_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(undo_actions).where(undo_actions.c.reverse_command_id == reverse_command_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def set_undo_action_reverse_command(
    connection: AsyncConnection, *, undo_id: uuid.UUID, reverse_command_id: uuid.UUID
) -> None:
    await connection.execute(
        update(undo_actions)
        .where(undo_actions.c.id == undo_id)
        .values(reverse_command_id=reverse_command_id)
    )


async def mark_undo_action_undone(
    connection: AsyncConnection, *, undo_id: uuid.UUID, undone_at: datetime
) -> None:
    await connection.execute(
        update(undo_actions).where(undo_actions.c.id == undo_id).values(undone_at=undone_at)
    )
