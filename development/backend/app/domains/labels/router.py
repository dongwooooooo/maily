import uuid

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.domains.identity.schemas import RequestContext
from app.domains.labels.schemas import (
    CreateLabelInput,
    MoveMessageInput,
    MoveMessageResult,
    ServiceLabel,
    UpdateLabelInput,
)
from app.domains.labels.service import (
    create_or_update_label,
    get_owned_label,
    list_labels,
    move_message_to_label,
    update_label,
)

# blanket prefix 없음. _integration-contract.md §3은 labels의 대표 endpoint를
# `GET/POST /labels`, `PATCH /labels/{id}`, `POST /messages/{id}/move`로 나열한다.
# 마지막 endpoint는 `/labels` path prefix를 공유하지 않으므로, 이 router는 full path를 선언하고
# app/api/router.py에서 prefix 없이 include된다.
router = APIRouter()


class CreateLabelRequest(BaseModel):
    connected_account_id: uuid.UUID
    name: str
    order_index: int | None = None
    hidden: bool = False


class UpdateLabelRequest(BaseModel):
    name: str | None = None
    order_index: int | None = None
    hidden: bool | None = None


class MoveMessageRequest(BaseModel):
    label_id: uuid.UUID


@router.post("/labels", response_model=ServiceLabel)
async def create_label(
    body: CreateLabelRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ServiceLabel:
    data = CreateLabelInput(workspace_id=context.workspace_id, **body.model_dump())
    label, _ = await create_or_update_label(connection, data)
    return label


@router.get("/labels", response_model=list[ServiceLabel])
async def get_labels(
    include_hidden: bool = False,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[ServiceLabel]:
    return await list_labels(
        connection, workspace_id=context.workspace_id, include_hidden=include_hidden
    )


@router.patch("/labels/{label_id}", response_model=ServiceLabel)
async def patch_label(
    label_id: uuid.UUID,
    body: UpdateLabelRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ServiceLabel:
    await get_owned_label(connection, label_id=label_id, workspace_id=context.workspace_id)
    changes = UpdateLabelInput(**body.model_dump(exclude_unset=True))
    return await update_label(connection, label_id=label_id, changes=changes)


@router.post("/messages/{message_id}/move", response_model=MoveMessageResult)
async def move_message(
    message_id: uuid.UUID,
    body: MoveMessageRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> MoveMessageResult:
    data = MoveMessageInput(
        workspace_id=context.workspace_id,
        message_id=message_id,
        label_id=body.label_id,
        actor_id=context.user_id,
        idempotency_key=idempotency_key,
    )
    return await move_message_to_label(connection, data)
