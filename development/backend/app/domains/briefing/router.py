import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.domains.briefing.item_state import set_item_seen
from app.domains.briefing.queries import get_message_detail, get_storage_upcoming, get_today_briefing
from app.domains.briefing.reminders import schedule_reminder
from app.domains.briefing.schemas import (
    AccountBriefingGroup,
    ItemStateResult,
    MessageDetail,
    ReminderResult,
    UpcomingStorage,
)
from app.domains.identity.schemas import RequestContext

# No blanket prefix — _integration-contract.md §3 lists this domain's
# representative endpoints under three different top-level paths
# (/briefing, /messages, /storage), like labels' router. Declares full
# paths and is included in app/api/router.py without a prefix.
router = APIRouter()


class RemindLaterRequest(BaseModel):
    remind_at: datetime


@router.get("/briefing/today", response_model=list[AccountBriefingGroup])
async def today_briefing(
    scope: str = "all",
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[AccountBriefingGroup]:
    return await get_today_briefing(connection, workspace_id=context.workspace_id, scope=scope)


@router.get("/messages/{message_id}", response_model=MessageDetail)
async def message_detail(
    message_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> MessageDetail:
    return await get_message_detail(
        connection, message_id=message_id, workspace_id=context.workspace_id
    )


@router.get("/storage/upcoming", response_model=UpcomingStorage)
async def storage_upcoming(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> UpcomingStorage:
    return await get_storage_upcoming(connection, workspace_id=context.workspace_id)


@router.post("/briefing/items/{briefing_item_id}/seen", response_model=ItemStateResult)
async def mark_item_seen(
    briefing_item_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ItemStateResult:
    result, _is_new = await set_item_seen(
        connection,
        briefing_item_id=briefing_item_id,
        actor_id=context.user_id,
        workspace_id=context.workspace_id,
    )
    return result


@router.post("/briefing/items/{briefing_item_id}/remind_later", response_model=ReminderResult)
async def remind_later(
    briefing_item_id: uuid.UUID,
    body: RemindLaterRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ReminderResult:
    return await schedule_reminder(
        connection,
        briefing_item_id=briefing_item_id,
        remind_at=body.remind_at,
        actor_id=context.user_id,
        workspace_id=context.workspace_id,
    )
