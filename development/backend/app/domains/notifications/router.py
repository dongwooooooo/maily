from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.domains.identity.schemas import RequestContext
from app.domains.notifications.schemas import (
    NotificationEvent,
    NotificationSubscription,
    SubscribeInput,
)
from app.domains.notifications.service import list_notifications, subscribe

# _integration-contract.md §3 prefix table: notifications -> "/notifications".
# Routes below declare "" and "/subscribe" and rely on that prefix (see
# app/api/router.py _PREFIX_BY_DOMAIN), mirroring mail_sources' router.
router = APIRouter()


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: dict


@router.get("", response_model=list[NotificationEvent])
async def get_notifications(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[NotificationEvent]:
    return await list_notifications(connection, workspace_id=context.workspace_id)


@router.post("/subscribe", response_model=NotificationSubscription)
async def subscribe_endpoint(
    body: SubscribeRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> NotificationSubscription:
    data = SubscribeInput(user_id=context.user_id, endpoint=body.endpoint, keys=body.keys)
    return await subscribe(connection, data)
