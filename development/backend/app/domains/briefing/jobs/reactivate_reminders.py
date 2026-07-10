"""`reactivate_reminders` job — docs/goals/backend-plans/briefing.md "Job:
reactivate_reminders". Scheduled (due-scan) trigger, payload `{}`,
lock_key null (_integration-contract.md §2).
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.outbox import append_event
from app.domains.briefing import events, repository

logger = structlog.get_logger()


async def run_reactivate_reminders(connection: AsyncConnection) -> list[uuid.UUID]:
    """Pick up every `pending` reminder whose `remind_at` has passed,
    transition it to `reactivated`, and emit `reminder_reactivated`.

    The conditional `WHERE status='pending'` update in
    repository.reactivate_reminder_if_pending is what makes this safe
    under concurrent scans (briefing.md §동시) and safe to re-run
    (§멱등 — an already-reactivated reminder's remind_at may still be in
    the past, but its status is no longer 'pending' so it's excluded from
    the next scan's candidate list before the conditional update even
    runs).
    """
    now = datetime.now(timezone.utc)
    due = await repository.list_due_pending_reminders(connection, now=now)

    reactivated_ids: list[uuid.UUID] = []
    for reminder in due:
        result = await repository.reactivate_reminder_if_pending(
            connection, reminder_id=reminder["id"], reactivated_at=now
        )
        if result is None:
            # Lost the race to another scan, or already reactivated —
            # [동시]/[멱등] guard, not an error.
            continue

        state = await repository.get_item_state(
            connection, item_state_id=result["briefing_item_state_id"]
        )
        if state is None:
            # briefing_item_state_id is a non-nullable FK with no delete
            # path today, so this shouldn't happen — but if it ever does
            # (mirrors gmail_actions execute_action._finalize_undo_if_
            # reverse's identical guard), skip publishing rather than
            # emit a workspace_id/message_id: null event that would only
            # fail once a worker later picks up the resulting job.
            logger.warning(
                "reminder의 item_state row가 사라져 reminder_reactivated 발행 생략",
                reminder_id=str(result["id"]),
            )
            reactivated_ids.append(result["id"])
            continue
        await append_event(
            connection,
            event_type=events.REMINDER_REACTIVATED,
            producer_domain="briefing",
            payload={
                "reminder_id": str(result["id"]),
                "briefing_item_state_id": str(result["briefing_item_state_id"]),
                "message_id": str(state["message_id"]),
                "workspace_id": str(state["workspace_id"]),
            },
            idempotency_key=events.reminder_reactivated_key(result["id"]),
        )
        reactivated_ids.append(result["id"])

    logger.info("리마인더 재활성화 스캔 완료", reactivated_count=len(reactivated_ids))
    return reactivated_ids


async def reactivate_reminders_job(payload: dict) -> None:
    """JOB_HANDLERS["reactivate_reminders"] entry point — see __init__.py."""
    from app.core.database import engine

    async with engine.begin() as connection:
        await run_reactivate_reminders(connection)
