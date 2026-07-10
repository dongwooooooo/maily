import uuid
from datetime import datetime

from pydantic import BaseModel


class RouteTarget(BaseModel):
    """"어느 화면 + 어느 selected item" — notifications.md 매핑표의 결과 shape.

    `screen`은 항상 존재한다(generic-landing-prohibition invariant —
    notifications.md "route_target이 비면(selected item 부재는 허용, 화면
    부재는 불가) 발행을 거부한다"). `item_id`는 screen-only notification(예: daily_briefing)에서
    None일 수 있다.
    """

    screen: str
    item_id: uuid.UUID | None = None


class NotificationEvent(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    notification_type: str
    route_target: RouteTarget
    read_at: datetime | None
    created_at: datetime


class SubscribeInput(BaseModel):
    user_id: uuid.UUID
    endpoint: str
    keys: dict


class NotificationSubscription(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    endpoint: str
    revoked_at: datetime | None
    # `keys`(push encryption material)는 response schema에서 의도적으로 제외한다.
    # notifications.md "[데이터경계] keys는 응답에 절대 미포함".
