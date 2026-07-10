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
    """새로 작성된 notification row에 대해 notification_event_created를 emit한다.

    consumer(_integration-contract.md §3 기준 browser push worker)는 active
    `notification_subscriptions`로 fan-out한다. 여기서는 범위 밖이다(POC는 fake push sink 사용,
    notifications.md "워크트리 격리 노트" 참고).
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
