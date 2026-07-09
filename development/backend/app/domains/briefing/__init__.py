import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.briefing.jobs.build_briefing import build_briefing_job
from app.domains.briefing.jobs.reactivate_reminders import reactivate_reminders_job
from app.domains.briefing.router import router as router

JOB_HANDLERS: dict = {
    "build_briefing": build_briefing_job,
    "reactivate_reminders": reactivate_reminders_job,
}

# _integration-contract.md §3 — which job(s) get queued for each event this
# domain consumes. Wiring the outbox dispatcher to actually call these
# (IC2/IC3) is a later coordinator step; this map documents the intended
# wiring per the contract table now so the coordinator doesn't have to
# reverse-engineer it from job docstrings.
EVENT_CONSUMERS: dict = {
    "gmail_snapshot_changed": ["build_briefing"],
    "gmail_action_applied": ["build_briefing"],
    "gmail_action_undone": ["build_briefing"],
    "summary_completed": ["build_briefing"],
    "importance_classified": ["build_briefing"],
    "reminder_reactivated": ["build_briefing"],
}


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    """PURGE_HANDLER(source_id) — _integration-contract.md §4.

    briefing_items/briefing_item_states are content-bearing (◆,
    db-schema.md) — purged on source disconnect (briefing.md "워크트리
    격리 노트"). briefing_item_states has no connected_account_id column
    (durable state deliberately references gmail_messages only, see
    models.py), so purge joins through gmail_messages to find the
    account's state rows; reminders cascade via briefing_item_state_id.
    """
    from app.domains.briefing.models import briefing_item_states, briefing_items, reminders
    from app.domains.mail_intake.models import gmail_messages

    await connection.execute(
        delete(briefing_items).where(briefing_items.c.connected_account_id == source_id)
    )

    state_ids = (
        await connection.execute(
            select(briefing_item_states.c.id)
            .select_from(
                briefing_item_states.join(
                    gmail_messages, gmail_messages.c.id == briefing_item_states.c.message_id
                )
            )
            .where(gmail_messages.c.connected_account_id == source_id)
        )
    ).scalars().all()
    if state_ids:
        await connection.execute(
            delete(reminders).where(reminders.c.briefing_item_state_id.in_(state_ids))
        )
        await connection.execute(
            delete(briefing_item_states).where(briefing_item_states.c.id.in_(state_ids))
        )


PURGE_HANDLER = purge_source
