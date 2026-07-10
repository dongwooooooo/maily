import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.core.errors import NotFoundError
from app.domains.identity.schemas import RequestContext
from app.domains.mail_sources import repository
from app.domains.mail_sources.schemas import (
    ConnectGmailSourceInput,
    ConnectedSource,
    DisconnectGmailSourceInput,
    DisconnectResult,
    SourceSettingsResult,
)
from app.domains.mail_sources.service import (
    connect_gmail_source,
    disconnect_gmail_source,
    update_gmail_source_settings,
)

router = APIRouter()


class ConnectSourceRequest(BaseModel):
    gmail_address: str
    access_token: str
    refresh_token: str
    scope: str
    expires_at: datetime


class UpdateSourceSettingsRequest(BaseModel):
    display_name: str | None = None
    briefing_enabled: bool | None = None
    summary_enabled: bool | None = None
    notification_enabled: bool | None = None
    paused: bool | None = None


async def _get_owned_account(
    connection: AsyncConnection, *, source_id: uuid.UUID, workspace_id: uuid.UUID
) -> dict:
    account = await repository.get_connected_account(connection, connected_account_id=source_id)
    if account is None or account["workspace_id"] != workspace_id:
        # 어느 경우든 404다. 다른 workspace source의 존재를 드러내지 않는다.
        raise NotFoundError("gmail source not found")
    return account


@router.post("", response_model=ConnectedSource)
async def connect_source(
    body: ConnectSourceRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ConnectedSource:
    data = ConnectGmailSourceInput(workspace_id=context.workspace_id, **body.model_dump())
    source, _ = await connect_gmail_source(connection, data)
    return source


@router.get("", response_model=list[ConnectedSource])
async def list_sources(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[ConnectedSource]:
    rows = await repository.list_active_sources(connection, workspace_id=context.workspace_id)
    return [ConnectedSource(**row) for row in rows]


@router.get("/{source_id}", response_model=ConnectedSource)
async def get_source(
    source_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ConnectedSource:
    account = await _get_owned_account(
        connection, source_id=source_id, workspace_id=context.workspace_id
    )
    return ConnectedSource(**account)


@router.patch("/{source_id}", response_model=SourceSettingsResult)
async def patch_source_settings(
    source_id: uuid.UUID,
    body: UpdateSourceSettingsRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> SourceSettingsResult:
    await _get_owned_account(connection, source_id=source_id, workspace_id=context.workspace_id)
    changes = body.model_dump(exclude_unset=True)
    return await update_gmail_source_settings(
        connection, connected_account_id=source_id, changes=changes
    )


@router.delete("/{source_id}", response_model=DisconnectResult)
async def disconnect_source(
    source_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> DisconnectResult:
    await _get_owned_account(connection, source_id=source_id, workspace_id=context.workspace_id)
    return await disconnect_gmail_source(
        connection,
        DisconnectGmailSourceInput(workspace_id=context.workspace_id, connected_account_id=source_id),
    )
