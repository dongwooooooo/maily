import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MessageSnapshot(BaseModel):
    id: uuid.UUID
    connected_account_id: uuid.UUID
    gmail_message_id: str
    gmail_thread_id: str
    subject: str | None
    sender: str | None
    received_at: datetime | None
    is_read: bool
    is_archived: bool
    snapshot_version: int


class SyncCursorResult(BaseModel):
    connected_account_id: uuid.UUID
    last_history_id: int | None
    watch_expiration_at: datetime | None
    last_successful_sync_at: datetime | None
    cursor_status: str


class SyncRunResult(BaseModel):
    id: uuid.UUID
    connected_account_id: uuid.UUID
    run_type: str
    trigger: str
    status: str
    messages_changed_count: int
    error_reason: str | None


class ManualSyncRequest(BaseModel):
    run_type: Literal["delta", "full"] = "delta"


class ManualSyncQueued(BaseModel):
    source_id: uuid.UUID
    job_type: str
    queued: bool
