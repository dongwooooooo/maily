import uuid
from datetime import datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.labels.models import (
    gmail_label_mappings,
    label_correction_signals,
    service_labels,
)
from app.domains.mail_intake.models import gmail_messages
from app.domains.mail_sources.models import connected_gmail_accounts


async def get_service_label_by_name(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, name: str
) -> dict | None:
    row = (
        await connection.execute(
            select(service_labels).where(
                service_labels.c.workspace_id == workspace_id, service_labels.c.name == name
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_service_label(connection: AsyncConnection, *, label_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(service_labels).where(service_labels.c.id == label_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_service_labels(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, include_hidden: bool
) -> list[dict]:
    stmt = select(service_labels).where(service_labels.c.workspace_id == workspace_id)
    if not include_hidden:
        stmt = stmt.where(service_labels.c.hidden.is_(False))
    stmt = stmt.order_by(service_labels.c.order_index.asc())
    rows = (await connection.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def next_order_index(connection: AsyncConnection, *, workspace_id: uuid.UUID) -> int:
    max_index = (
        await connection.execute(
            select(func.max(service_labels.c.order_index)).where(
                service_labels.c.workspace_id == workspace_id
            )
        )
    ).scalar()
    return 0 if max_index is None else max_index + 1


async def insert_service_label(
    connection: AsyncConnection,
    *,
    label_id: uuid.UUID,
    workspace_id: uuid.UUID,
    name: str,
    order_index: int,
    hidden: bool,
    updated_at: datetime,
) -> None:
    await connection.execute(
        insert(service_labels).values(
            id=label_id,
            workspace_id=workspace_id,
            name=name,
            order_index=order_index,
            hidden=hidden,
            updated_at=updated_at,
        )
    )


async def update_service_label(
    connection: AsyncConnection,
    *,
    label_id: uuid.UUID,
    name: str,
    order_index: int,
    hidden: bool,
    updated_at: datetime,
) -> None:
    await connection.execute(
        update(service_labels)
        .where(service_labels.c.id == label_id)
        .values(name=name, order_index=order_index, hidden=hidden, updated_at=updated_at)
    )


async def get_gmail_label_mapping(
    connection: AsyncConnection, *, service_label_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_label_mappings).where(
                gmail_label_mappings.c.service_label_id == service_label_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def insert_gmail_label_mapping(
    connection: AsyncConnection,
    *,
    mapping_id: uuid.UUID,
    service_label_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    gmail_label_name: str,
) -> None:
    await connection.execute(
        insert(gmail_label_mappings).values(
            id=mapping_id,
            service_label_id=service_label_id,
            connected_account_id=connected_account_id,
            gmail_label_id=None,
            gmail_label_name=gmail_label_name,
        )
    )


async def update_gmail_label_mapping_name(
    connection: AsyncConnection, *, service_label_id: uuid.UUID, gmail_label_name: str
) -> None:
    await connection.execute(
        update(gmail_label_mappings)
        .where(gmail_label_mappings.c.service_label_id == service_label_id)
        .values(gmail_label_name=gmail_label_name)
    )


async def get_connected_account_status(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> str | None:
    """mail_sources account status에 대한 read-only cross-domain lookup.

    labels는 connected_gmail_accounts를 소유하지 않지만, create_or_update_label과
    move_message_to_label은 disconnected/disconnecting account를 대상으로 하는 요청을 모두
    거부해야 한다(module-boundaries.md §invariant). 이는 service call이 아니라 plain read이며,
    write side effect가 domain boundary를 넘지 않는다.
    """
    row = (
        await connection.execute(
            select(connected_gmail_accounts.c.status).where(
                connected_gmail_accounts.c.id == connected_account_id
            )
        )
    ).first()
    return row[0] if row is not None else None


async def get_message(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_messages).where(gmail_messages.c.id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_message_workspace(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> uuid.UUID | None:
    row = (
        await connection.execute(
            select(connected_gmail_accounts.c.workspace_id)
            .select_from(gmail_messages)
            .join(
                connected_gmail_accounts,
                connected_gmail_accounts.c.id == gmail_messages.c.connected_account_id,
            )
            .where(gmail_messages.c.id == message_id)
        )
    ).first()
    return row[0] if row is not None else None


async def count_label_correction_signals(
    connection: AsyncConnection, *, message_id: uuid.UUID, service_label_id: uuid.UUID
) -> int:
    count = (
        await connection.execute(
            select(func.count())
            .select_from(label_correction_signals)
            .where(
                label_correction_signals.c.message_id == message_id,
                label_correction_signals.c.service_label_id == service_label_id,
            )
        )
    ).scalar()
    return count or 0


async def insert_label_correction_signal(
    connection: AsyncConnection,
    *,
    signal_id: uuid.UUID,
    message_id: uuid.UUID,
    service_label_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    await connection.execute(
        insert(label_correction_signals).values(
            id=signal_id,
            message_id=message_id,
            service_label_id=service_label_id,
            actor_id=actor_id,
        )
    )
