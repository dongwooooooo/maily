import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.mail_sources.models import gmail_source_settings
from app.domains.notifications.models import notification_events, notification_subscriptions


async def get_source_notification_enabled(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> bool:
    """mail_sources own settings table에 대한 read-only cross-domain lookup.

    notifications는 gmail_source_settings를 소유하지 않는다. 이는 service call이 아니라 plain
    read이며, upstream domain table을 직접 읽는 labels.repository.get_connected_account_status의
    precedent를 mirror한다. settings row가 없으면(account가 설정된 적 없거나 test에서 row 없이
    seed됨) enabled가 default이며, column 자체의 `server_default="true"`와 일치한다.
    """
    row = (
        await connection.execute(
            select(gmail_source_settings.c.notification_enabled).where(
                gmail_source_settings.c.connected_account_id == connected_account_id
            )
        )
    ).first()
    return True if row is None else bool(row[0])


async def insert_notification_event(
    connection: AsyncConnection,
    *,
    notification_id: uuid.UUID,
    workspace_id: uuid.UUID,
    notification_type: str,
    route_target: dict,
    created_at: datetime,
) -> None:
    await connection.execute(
        notification_events.insert().values(
            id=notification_id,
            workspace_id=workspace_id,
            notification_type=notification_type,
            route_target=route_target,
            read_at=None,
            created_at=created_at,
        )
    )


async def get_notification_event(
    connection: AsyncConnection, *, notification_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(notification_events).where(notification_events.c.id == notification_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_notification_events(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[dict]:
    # [필터] 미확인(read_at null) 우선, 그다음 최신순 — notifications.md
    # "GET /notifications [필터]".
    stmt = (
        select(notification_events)
        .where(notification_events.c.workspace_id == workspace_id)
        .order_by(
            notification_events.c.read_at.is_not(None),
            notification_events.c.created_at.desc(),
        )
    )
    rows = (await connection.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def upsert_subscription(
    connection: AsyncConnection,
    *,
    subscription_id: uuid.UUID,
    user_id: uuid.UUID,
    endpoint: str,
    keys: dict,
) -> uuid.UUID:
    """push subscription을 register하거나 같은 `endpoint`의 기존 row를 refresh한다.

    notifications.md "[멱등] 같은 endpoint 재구독 ... 기존 row 갱신(keys 갱신, revoked_at 초기화)
    → 중복 row 안 생김."

    현재 유효한 row의 id를 반환한다(first subscribe면 new id, resubscribe면 기존 row id).
    """
    stmt = (
        insert(notification_subscriptions)
        .values(
            id=subscription_id,
            user_id=user_id,
            endpoint=endpoint,
            keys=keys,
            revoked_at=None,
        )
        .on_conflict_do_update(
            constraint="uq_notification_subscriptions_endpoint",
            set_={"user_id": user_id, "keys": keys, "revoked_at": None},
        )
        .returning(notification_subscriptions.c.id)
    )
    result = await connection.execute(stmt)
    return result.scalar_one()


async def get_subscription(
    connection: AsyncConnection, *, subscription_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(notification_subscriptions).where(
                notification_subscriptions.c.id == subscription_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None
