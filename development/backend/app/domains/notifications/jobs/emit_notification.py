"""`emit_notification` job — docs/goals/backend-plans/notifications.md
"Command/Job: emit_notification".

개념적으로 gmail_source_recovery_needed, gmail_action_failed, cleanup_proposal_created,
reminder_reactivated가 trigger한다(app/domains/notifications/__init__.py EVENT_CONSUMERS 참고).
이 event들의 outbox->job_runs dispatch wiring은 caller instruction 기준 IC7의 job이다. 이
task는 handler function만 직접 wire/test하며, live event에서 dispatch되는 대신
`{trigger, payload}`를 받는다(_integration-contract.md §2의 literal job payload shape와 다른
이유는 service.py module docstring "Payload contract note" 참고).
"""

import uuid

import structlog

from app.domains.notifications.service import emit_notification

logger = structlog.get_logger()


async def run_emit_notification(connection, *, trigger: str, payload: dict) -> uuid.UUID | None:
    return await emit_notification(connection, trigger=trigger, payload=payload)


async def emit_notification_job(payload: dict) -> None:
    """JOB_HANDLERS["emit_notification"] entry point — __init__.py 참고.

    `payload`는 job_runs row 자체의 payload다:
    `{"trigger": <event type>, "payload": <that event's raw payload dict>}`.
    """
    from app.core.database import engine

    trigger = payload["trigger"]
    event_payload = payload["payload"]
    async with engine.begin() as connection:
        await run_emit_notification(connection, trigger=trigger, payload=event_payload)
