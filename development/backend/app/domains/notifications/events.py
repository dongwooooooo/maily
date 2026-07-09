import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.outbox import append_event

NOTIFICATION_EVENT_CREATED = "notification_event_created"


def created_key(notification_id: uuid.UUID) -> str:
    return f"notification:{notification_id}:created"


async def record_notification_event_created(
    connection: AsyncConnection,
    *,
    notification_id: uuid.UUID,
    workspace_id: uuid.UUID,
    notification_type: str,
    route_target: dict,
) -> uuid.UUID | None:
    """Emit notification_event_created for a newly written notification row.

    Consumer (browser push worker, per _integration-contract.md §3) fans
    out to active `notification_subscriptions` — out of scope here (POC
    uses a fake push sink, see notifications.md "워크트리 격리 노트").
    """
    return await append_event(
        connection,
        event_type=NOTIFICATION_EVENT_CREATED,
        producer_domain="notifications",
        payload={
            "notification_id": str(notification_id),
            "workspace_id": str(workspace_id),
            "notification_type": notification_type,
            "route_target": route_target,
        },
        idempotency_key=created_key(notification_id),
    )
