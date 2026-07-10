import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ValidationError
from app.core.outbox import append_event
from app.domains.briefing import events, repository
from app.domains.briefing.item_state import resolve_owned_briefing_item
from app.domains.briefing.schemas import ReminderResult

logger = structlog.get_logger()


async def schedule_reminder(
    connection: AsyncConnection,
    *,
    briefing_item_id: uuid.UUID,
    remind_at: datetime,
    actor_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> ReminderResult:
    """Command `schedule_reminder` — docs/goals/backend-plans/briefing.md.

    Rejects a past `remind_at` (§선행조건: POC 정책은 거부, not immediate
    reactivation). A reschedule of the same item always updates the
    existing pending `reminders` row instead of inserting a second one
    (§멱등 — "중복 pending row 금지"); a terminal (reactivated/cancelled)
    reminder is never reused (§상태 전이).
    """
    item = await resolve_owned_briefing_item(
        connection, briefing_item_id=briefing_item_id, workspace_id=workspace_id
    )
    now = datetime.now(timezone.utc)
    if remind_at <= now:
        raise ValidationError("remind_at must be in the future")

    message_id = item["message_id"]
    existing_state = await repository.get_item_state_by_message(connection, message_id=message_id)

    unchanged = existing_state is not None and existing_state["remind_later_at"] == remind_at
    state_id = existing_state["id"] if existing_state is not None else uuid.uuid4()
    seen = existing_state["seen"] if existing_state is not None else False
    seen_at = existing_state["seen_at"] if existing_state is not None else None

    if unchanged:
        version = existing_state["version"]
        updated_at = existing_state["updated_at"]
    else:
        version = (existing_state["version"] + 1) if existing_state is not None else 1
        updated_at = now

    await repository.upsert_item_state(
        connection,
        state_id=state_id,
        workspace_id=workspace_id,
        message_id=message_id,
        seen=seen,
        seen_at=seen_at,
        remind_later_at=remind_at,
        version=version,
        updated_at=updated_at,
    )
    if not unchanged:
        await append_event(
            connection,
            event_type=events.ITEM_STATE_CHANGED,
            producer_domain="briefing",
            payload={
                "briefing_item_state_id": str(state_id),
                "message_id": str(message_id),
                "remind_later_at": remind_at.isoformat(),
            },
            idempotency_key=events.item_state_changed_key(state_id, version),
        )

    pending = await repository.get_pending_reminder_by_state(
        connection, briefing_item_state_id=state_id
    )
    if pending is not None:
        await repository.update_reminder_remind_at(
            connection, reminder_id=pending["id"], remind_at=remind_at
        )
        reminder_id = pending["id"]
    else:
        reminder_id = uuid.uuid4()
        await repository.insert_reminder(
            connection,
            reminder_id=reminder_id,
            briefing_item_state_id=state_id,
            remind_at=remind_at,
        )

    logger.info(
        "리마인더 예약",
        message_id=str(message_id),
        remind_at=remind_at.isoformat(),
        actor_id=str(actor_id),
    )
    return ReminderResult(
        id=reminder_id,
        briefing_item_state_id=state_id,
        remind_at=remind_at,
        reactivated_at=None,
        status="pending",
    )
