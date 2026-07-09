import uuid
from datetime import datetime

from sqlalchemy import and_, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.briefing.models import briefing_item_states, briefing_items, reminders
from app.domains.mail_intake.models import gmail_messages, message_excerpts
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings

# ---- source/message lookups (read-only joins into upstream domains) -------


async def get_message(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_messages).where(gmail_messages.c.id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_message_excerpt(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(message_excerpts).where(message_excerpts.c.message_id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_connected_account(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(
                connected_gmail_accounts.c.id,
                connected_gmail_accounts.c.workspace_id,
                connected_gmail_accounts.c.gmail_address,
                connected_gmail_accounts.c.status,
            ).where(connected_gmail_accounts.c.id == connected_account_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_connected_accounts_for_workspace(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, source_id: uuid.UUID | None = None
) -> list[dict]:
    """Accounts + their gmail_source_settings.briefing_enabled, defaulting to
    True when no settings row exists yet (briefing does not own that row's
    creation — mail_sources does)."""
    query = (
        select(
            connected_gmail_accounts.c.id,
            connected_gmail_accounts.c.workspace_id,
            connected_gmail_accounts.c.gmail_address,
            connected_gmail_accounts.c.status,
            gmail_source_settings.c.briefing_enabled,
        )
        .select_from(
            connected_gmail_accounts.outerjoin(
                gmail_source_settings,
                gmail_source_settings.c.connected_account_id == connected_gmail_accounts.c.id,
            )
        )
        .where(connected_gmail_accounts.c.workspace_id == workspace_id)
    )
    if source_id is not None:
        query = query.where(connected_gmail_accounts.c.id == source_id)
    rows = (await connection.execute(query)).mappings().all()
    return [
        {**dict(row), "briefing_enabled": True if row["briefing_enabled"] is None else row["briefing_enabled"]}
        for row in rows
    ]


async def list_messages_for_account(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> list[dict]:
    rows = (
        await connection.execute(
            select(gmail_messages).where(
                gmail_messages.c.connected_account_id == connected_account_id
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# ---- briefing_items (regenerable projection) -------------------------------


async def upsert_briefing_item(
    connection: AsyncConnection,
    *,
    item_id: uuid.UUID,
    workspace_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    message_id: uuid.UUID,
    section: str,
    importance_band: str | None,
    summary_text: str | None,
    rebuilt_at: datetime,
) -> None:
    stmt = pg_insert(briefing_items).values(
        id=item_id,
        workspace_id=workspace_id,
        connected_account_id=connected_account_id,
        message_id=message_id,
        section=section,
        importance_band=importance_band,
        summary_text=summary_text,
        rebuilt_at=rebuilt_at,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_briefing_items_account_message",
        set_={
            "section": stmt.excluded.section,
            "importance_band": stmt.excluded.importance_band,
            "summary_text": stmt.excluded.summary_text,
            "rebuilt_at": stmt.excluded.rebuilt_at,
        },
    )
    await connection.execute(stmt)


async def get_briefing_item(connection: AsyncConnection, *, item_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(select(briefing_items).where(briefing_items.c.id == item_id))
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_briefing_item_by_account_message(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID, message_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(briefing_items).where(
                and_(
                    briefing_items.c.connected_account_id == connected_account_id,
                    briefing_items.c.message_id == message_id,
                )
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_briefing_items_for_account(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> list[dict]:
    rows = (
        await connection.execute(
            select(briefing_items).where(
                briefing_items.c.connected_account_id == connected_account_id
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_briefing_cards_for_account(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> list[dict]:
    """briefing_items joined with gmail_messages (raw fields, live join —
    not denormalized, see models.py) and briefing_item_states (seen flag,
    durable — joined by message_id so it survives projection rebuilds)."""
    query = (
        select(
            briefing_items.c.id,
            briefing_items.c.connected_account_id,
            briefing_items.c.message_id,
            briefing_items.c.section,
            briefing_items.c.importance_band,
            briefing_items.c.summary_text,
            briefing_items.c.rebuilt_at,
            gmail_messages.c.subject,
            gmail_messages.c.sender,
            gmail_messages.c.snippet,
            gmail_messages.c.received_at,
            gmail_messages.c.is_read,
            gmail_messages.c.is_archived,
            briefing_item_states.c.seen,
        )
        .select_from(
            briefing_items.join(
                gmail_messages, gmail_messages.c.id == briefing_items.c.message_id
            ).outerjoin(
                briefing_item_states,
                briefing_item_states.c.message_id == briefing_items.c.message_id,
            )
        )
        .where(briefing_items.c.connected_account_id == connected_account_id)
        .order_by(gmail_messages.c.received_at.desc())
    )
    rows = (await connection.execute(query)).mappings().all()
    return [{**dict(row), "seen": bool(row["seen"])} for row in rows]


async def delete_briefing_items_for_workspace(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> None:
    """Test/ops utility only — proves briefing_items is drop-and-rebuild
    safe (briefing.md 강제 invariant). Never called from request-serving
    code paths."""
    from sqlalchemy import delete

    await connection.execute(
        delete(briefing_items).where(briefing_items.c.workspace_id == workspace_id)
    )


# ---- briefing_item_states (durable) ----------------------------------------


async def get_item_state_by_message(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(briefing_item_states).where(
                briefing_item_states.c.message_id == message_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_item_state(connection: AsyncConnection, *, item_state_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(briefing_item_states).where(briefing_item_states.c.id == item_state_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def upsert_item_state(
    connection: AsyncConnection,
    *,
    state_id: uuid.UUID,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    seen: bool,
    seen_at: datetime | None,
    remind_later_at: datetime | None,
    version: int,
    updated_at: datetime,
) -> None:
    stmt = pg_insert(briefing_item_states).values(
        id=state_id,
        workspace_id=workspace_id,
        message_id=message_id,
        seen=seen,
        seen_at=seen_at,
        remind_later_at=remind_later_at,
        version=version,
        updated_at=updated_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[briefing_item_states.c.message_id],
        set_={
            "seen": stmt.excluded.seen,
            "seen_at": stmt.excluded.seen_at,
            "remind_later_at": stmt.excluded.remind_later_at,
            "version": stmt.excluded.version,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await connection.execute(stmt)


# ---- reminders --------------------------------------------------------------


async def insert_reminder(
    connection: AsyncConnection,
    *,
    reminder_id: uuid.UUID,
    briefing_item_state_id: uuid.UUID,
    remind_at: datetime,
) -> None:
    await connection.execute(
        insert(reminders).values(
            id=reminder_id,
            briefing_item_state_id=briefing_item_state_id,
            remind_at=remind_at,
            reactivated_at=None,
            status="pending",
        )
    )


async def get_pending_reminder_by_state(
    connection: AsyncConnection, *, briefing_item_state_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(reminders).where(
                and_(
                    reminders.c.briefing_item_state_id == briefing_item_state_id,
                    reminders.c.status == "pending",
                )
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def update_reminder_remind_at(
    connection: AsyncConnection, *, reminder_id: uuid.UUID, remind_at: datetime
) -> None:
    await connection.execute(
        update(reminders).where(reminders.c.id == reminder_id).values(remind_at=remind_at)
    )


async def list_due_pending_reminders(
    connection: AsyncConnection, *, now: datetime
) -> list[dict]:
    rows = (
        await connection.execute(
            select(reminders).where(
                and_(reminders.c.status == "pending", reminders.c.remind_at <= now)
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def reactivate_reminder_if_pending(
    connection: AsyncConnection, *, reminder_id: uuid.UUID, reactivated_at: datetime
) -> dict | None:
    """Conditional UPDATE ... WHERE status='pending' ... RETURNING — the
    concurrency guard from briefing.md "Job: reactivate_reminders" §동시:
    two concurrent scans racing on the same reminder only let one caller
    observe a non-None result."""
    stmt = (
        update(reminders)
        .where(and_(reminders.c.id == reminder_id, reminders.c.status == "pending"))
        .values(status="reactivated", reactivated_at=reactivated_at)
        .returning(reminders)
    )
    row = (await connection.execute(stmt)).mappings().first()
    return dict(row) if row is not None else None


async def list_pending_reminders_for_workspace(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[dict]:
    query = (
        select(
            reminders.c.id.label("reminder_id"),
            reminders.c.remind_at,
            briefing_item_states.c.message_id,
        )
        .select_from(
            reminders.join(
                briefing_item_states,
                briefing_item_states.c.id == reminders.c.briefing_item_state_id,
            )
        )
        .where(
            and_(
                reminders.c.status == "pending",
                briefing_item_states.c.workspace_id == workspace_id,
            )
        )
        .order_by(reminders.c.remind_at.asc())
    )
    rows = (await connection.execute(query)).mappings().all()
    return [dict(row) for row in rows]
