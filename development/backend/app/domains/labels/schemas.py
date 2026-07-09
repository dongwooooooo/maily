import uuid
from datetime import datetime

from pydantic import BaseModel


class CreateLabelInput(BaseModel):
    workspace_id: uuid.UUID
    connected_account_id: uuid.UUID
    name: str
    order_index: int | None = None
    hidden: bool = False


class UpdateLabelInput(BaseModel):
    name: str | None = None
    order_index: int | None = None
    hidden: bool | None = None


class ServiceLabel(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    order_index: int
    hidden: bool
    updated_at: datetime
    connected_account_id: uuid.UUID
    gmail_label_id: str | None
    gmail_label_name: str


class MoveMessageInput(BaseModel):
    workspace_id: uuid.UUID
    message_id: uuid.UUID
    label_id: uuid.UUID
    actor_id: uuid.UUID
    idempotency_key: str


class MoveMessageResult(BaseModel):
    correction_signal_id: uuid.UUID
    message_id: uuid.UUID
    service_label_id: uuid.UUID
    version: int
