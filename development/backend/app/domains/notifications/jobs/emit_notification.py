"""`emit_notification` job — docs/goals/backend-plans/notifications.md
"Command/Job: emit_notification".

Triggered (conceptually) by gmail_source_recovery_needed,
gmail_action_failed, cleanup_proposal_created, and reminder_reactivated
(see app/domains/notifications/__init__.py EVENT_CONSUMERS). The
outbox->job_runs dispatch wiring for these events is IC7's job (per
caller instructions) — this task only wires and tests the handler
function directly, taking `{trigger, payload}` rather than being
dispatched from a live event (see service.py module docstring "Payload
contract note" for why this differs from _integration-contract.md §2's
literal job payload shape).
"""

import uuid

import structlog

from app.domains.notifications.service import emit_notification

logger = structlog.get_logger()


async def run_emit_notification(connection, *, trigger: str, payload: dict) -> uuid.UUID | None:
    return await emit_notification(connection, trigger=trigger, payload=payload)


async def emit_notification_job(payload: dict) -> None:
    """JOB_HANDLERS["emit_notification"] entry point — see __init__.py.

    `payload` is the job_runs row's own payload: `{"trigger": <event
    type>, "payload": <that event's raw payload dict>}`.
    """
    from app.core.database import engine

    trigger = payload["trigger"]
    event_payload = payload["payload"]
    async with engine.begin() as connection:
        await run_emit_notification(connection, trigger=trigger, payload=event_payload)
