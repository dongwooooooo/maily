"""mail_intake-owned outbox events.

module-boundaries.md Event Catalog: `gmail_snapshot_changed`,
`gmail_notification_received`, and the mail_intake side of the jointly
owned `gmail_source_recovery_needed`. mail_intake appends these and never
calls another domain directly — consumers pick them up via the outbox
dispatcher (out of this task's scope, see _integration-contract.md §3).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.outbox import append_event


async def publish_snapshot_changed(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    message_ids: list[uuid.UUID],
) -> None:
    """A sync_run with an empty message_ids set does not publish — an empty
    event would just wake every consumer for nothing (mail_intake.md
    "메시지_ids가 빈 sync_run은 event를 발행하지 않는다")."""
    if not message_ids:
        return
    await append_event(
        connection,
        event_type="gmail_snapshot_changed",
        producer_domain="mail_intake",
        payload={
            "source_id": str(connected_account_id),
            "sync_run_id": str(sync_run_id),
            "message_ids": [str(message_id) for message_id in message_ids],
        },
        idempotency_key=f"source:{connected_account_id}:snapshot:{sync_run_id}",
    )


async def publish_notification_received(
    connection: AsyncConnection, *, email_address: str, history_id: int
) -> None:
    await append_event(
        connection,
        event_type="gmail_notification_received",
        producer_domain="mail_intake",
        payload={"email_address": email_address, "history_id": history_id},
        idempotency_key=f"gmail-notification:{email_address}:{history_id}",
    )


async def publish_recovery_needed(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    reason: str,
    version: int,
) -> None:
    """`reason` in {"auth_error", "scope_reduced", "watch_failed"} per
    mail_intake.md. `version` is the connected_gmail_accounts.version the
    caller already loaded (mail_sources owns that counter) — used as the
    idempotency disambiguator so a repeated failure at the same account
    version doesn't re-notify."""
    await append_event(
        connection,
        event_type="gmail_source_recovery_needed",
        producer_domain="mail_intake",
        payload={"source_id": str(connected_account_id), "reason": reason},
        idempotency_key=f"source:{connected_account_id}:recovery:{reason}:{version}",
    )
