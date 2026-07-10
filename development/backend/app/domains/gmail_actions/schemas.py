import uuid
from datetime import datetime

from pydantic import BaseModel

# action_type catalog — payload shape는 모두 동일하다
# (docs/goals/backend-plans/gmail_actions.md "Command: request_gmail_action") 기준.
SUPPORTED_ACTION_TYPES = {"mark_read", "archive", "read_and_archive", "label_apply"}

# status enum은 docs/goals/backend-plans/_integration-contract.md §5로 고정된다.
COMMAND_STATUSES = {"pending", "applied", "failed", "compensating", "undone"}


class RequestGmailActionInput(BaseModel):
    workspace_id: uuid.UUID
    connected_account_id: uuid.UUID
    message_id: uuid.UUID | None = None
    action_type: str
    gmail_label_id: str | None = None
    idempotency_key: str
    requested_by: uuid.UUID


class GmailActionCommand(BaseModel):
    id: uuid.UUID
    connected_account_id: uuid.UUID
    message_id: uuid.UUID | None
    action_type: str
    payload: dict
    status: str
    version: int
    changed: bool | None
    requested_by: uuid.UUID
    requested_at: datetime
    applied_at: datetime | None
    failed_at: datetime | None
    error_reason: str | None


class ActivityLogEntry(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    command_id: uuid.UUID | None
    action_summary: str
    actor_id: uuid.UUID | None
    occurred_at: datetime
    undo_available: bool
    undone_at: datetime | None


class UndoResult(BaseModel):
    id: uuid.UUID
    activity_id: uuid.UUID
    original_command_id: uuid.UUID
    reverse_command_id: uuid.UUID | None
    undo_available: bool
    undone_at: datetime | None
