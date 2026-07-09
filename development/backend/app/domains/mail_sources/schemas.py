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
