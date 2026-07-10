import uuid
from datetime import datetime

from sqlalchemy import and_, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.assistant_decisions.models import (
    message_importance_classifications,
    message_summaries,
)
from app.domains.briefing.models import briefing_item_states, briefing_items, reminders
from app.domains.mail_intake.models import gmail_messages, message_excerpts
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings

# ---- source/message lookup (upstream domain으로 read-only join) -------------


async def get_message_summary(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(message_summaries).where(message_summaries.c.message_id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_message_importance(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(message_importance_classifications).where(
                message_importance_classifications.c.message_id == message_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


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
    """account와 해당 gmail_source_settings.briefing_enabled를 반환한다.

    settings row가 아직 없으면 True가 default다(briefing은 그 row 생성을 소유하지 않고
    mail_sources가 소유한다).
    """
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


# ---- briefing_items (재생성 가능한 projection) -----------------------------


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
    """briefing_items를 gmail_messages 및 briefing_item_states와 join한다.

    gmail_messages는 raw field live join이며 denormalize하지 않는다(models.py 참고).
    briefing_item_states는 seen flag를 가진 durable state이며, projection rebuild 이후에도
    살아남도록 message_id로 join한다.
    """
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
    """test/ops utility 전용이다.

    briefing_items가 drop-and-rebuild safe임을 증명한다(briefing.md 강제 invariant).
    request-serving code path에서는 절대 호출하지 않는다.
    """
    from sqlalchemy import delete

    await connection.execute(
        delete(briefing_items).where(briefing_items.c.workspace_id == workspace_id)
    )


# ---- briefing_item_states(durable) 관리 ------------------------------------


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


# ---- reminders 관리 ---------------------------------------------------------


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
    """Conditional UPDATE ... WHERE status='pending' ... RETURNING은
    briefing.md "Job: reactivate_reminders" §동시의 concurrency guard다.
    같은 reminder를 두 concurrent scan이 동시에 잡아도 한 caller만 non-None
    result를 관측한다."""
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
