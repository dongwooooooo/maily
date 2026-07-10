import uuid
from datetime import datetime

from pydantic import BaseModel


class ConnectGmailSourceInput(BaseModel):
    workspace_id: uuid.UUID
    gmail_address: str
    access_token: str
    refresh_token: str
    scope: str
    expires_at: datetime


class ConnectedSource(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    gmail_address: str
    display_name: str | None
    status: str
    connected_at: datetime


class SourceSettingsResult(BaseModel):
    connected_account_id: uuid.UUID
    gmail_address: str
    display_name: str | None
    effective_display_name: str
    status: str
    briefing_enabled: bool
    summary_enabled: bool
    notification_enabled: bool
    paused: bool


class DisconnectGmailSourceInput(BaseModel):
    workspace_id: uuid.UUID
    connected_account_id: uuid.UUID


class DisconnectResult(BaseModel):
    connected_account_id: uuid.UUID
    status: str
