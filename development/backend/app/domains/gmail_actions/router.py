import uuid

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.core.errors import ValidationError
from app.domains.gmail_actions.activity import list_activity
from app.domains.gmail_actions.schemas import (
    ActivityLogEntry,
    GmailActionCommand,
    RequestGmailActionInput,
    UndoResult,
)
from app.domains.gmail_actions.service import request_gmail_action
from app.domains.gmail_actions.undo import request_undo
from app.domains.identity.schemas import RequestContext

router = APIRouter()


class CreateActionRequest(BaseModel):
    connected_account_id: uuid.UUID
    message_id: uuid.UUID | None = None
    action_type: str
    gmail_label_id: str | None = None


@router.post("", response_model=GmailActionCommand)
async def create_action(
    body: CreateActionRequest,
    # required(기본값 없음) — OpenAPI 스펙에 필수로 나가 프론트 codegen이
    # 타입 수준에서 강제한다. 빈 문자열은 아래 가드가 거른다.
    idempotency_key: str = Header(alias="Idempotency-Key"),
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> GmailActionCommand:
    if not idempotency_key:
        raise ValidationError("Idempotency-Key header is required")

    data = RequestGmailActionInput(
        workspace_id=context.workspace_id,
        connected_account_id=body.connected_account_id,
        message_id=body.message_id,
        action_type=body.action_type,
        gmail_label_id=body.gmail_label_id,
        idempotency_key=idempotency_key,
        requested_by=context.user_id,
    )
    command, _ = await request_gmail_action(connection, data)
    return command


@router.get("/activity", response_model=list[ActivityLogEntry])
async def get_activity(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[ActivityLogEntry]:
    return await list_activity(connection, workspace_id=context.workspace_id)


@router.post("/{activity_id}/undo", response_model=UndoResult)
async def undo_action(
    activity_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> UndoResult:
    return await request_undo(
        connection,
        activity_id=activity_id,
        workspace_id=context.workspace_id,
        actor_id=context.user_id,
    )
