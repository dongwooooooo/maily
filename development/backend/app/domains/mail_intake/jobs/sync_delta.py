import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=sync_delta, payload={source_id, start_history_id}.
    Triggered by gmail_notification_received (dedupe'd) or poll_history
    fallback. `trigger` isn't part of the job_registry payload shape
    (_integration-contract.md §2), so it's inferred here as "notification"
    — callers that need "poll" recorded on sync_runs.trigger should call
    service.sync_delta directly with trigger="poll" instead of going
    through this job wrapper (poll_history.py does exactly that today by
    calling service.poll_history, which enqueues this job for the
    notification-shaped payload)."""
    connected_account_id = uuid.UUID(payload["source_id"])
    start_history_id = int(payload["start_history_id"])
    async with engine.begin() as connection:
        await service.sync_delta(
            connection,
            connected_account_id=connected_account_id,
            start_history_id=start_history_id,
            trigger=payload.get("trigger", "notification"),
        )
