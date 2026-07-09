"""GmailReaderPort: the only way mail_intake reads Gmail data.

module-boundaries.md invariant: "Gmail read/sync 호출은 mail_intake의
GmailReaderPort ... 를 통해서만 한다." repository/service/job code must
depend on this abstract type, never on a concrete Gmail SDK client.

Every method receives a `connected_account_id` only — never a raw OAuth
token. Implementations resolve credentials through a handle mail_sources
injects (see live_reader.py). No method here may return a Gmail message
body: the only text field ever returned is Gmail's short `snippet`
(what `messages.get(format=metadata)` already includes), never
`format=full` content. See mail_intake.md "Port 계약" for the full
behavioral contract each method must satisfy.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypedDict


class HistoryRecord(TypedDict):
    record_type: str  # "message_added" | "message_deleted" | "labels_added" | "labels_removed"
    gmail_message_id: str
    label_ids: list[str]


class HistoryResult(TypedDict):
    records: list[HistoryRecord]
    new_history_id: int
    valid: bool


class MessageMetadata(TypedDict):
    subject: str | None
    sender: str | None
    snippet: str | None
    thread_id: str
    label_ids: list[str]
    is_read: bool
    is_archived: bool
    received_at: datetime | None


class WatchRegistration(TypedDict):
    topic_name: str
    expiration: datetime
    history_id: int


class MessageIdList(TypedDict):
    gmail_message_id: list[str]
    history_id: int


class GmailAuthError(Exception):
    """Raised by a reader implementation when Gmail rejects the credential
    (401/403, scope reduction). Callers (service/job code) catch this
    specifically to emit `gmail_source_recovery_needed` instead of treating
    it as a generic sync failure — mail_intake never writes account status
    itself (that stays owned by mail_sources)."""

    def __init__(self, message: str, *, reason: str = "auth_error"):
        super().__init__(message)
        self.reason = reason


class GmailReaderPort(ABC):
    """Read/sync-only access to Gmail. No mutation methods exist here —
    write access is `gmail_actions`' `GmailMutationPort`, a different port
    owned by a different domain."""

    @abstractmethod
    async def register_watch(self, connected_account_id: uuid.UUID) -> WatchRegistration:
        """Register (or re-register) a Pub/Sub watch for this account."""

    @abstractmethod
    async def history(
        self, connected_account_id: uuid.UUID, start_history_id: int | None
    ) -> HistoryResult:
        """List history records since `start_history_id`.

        `valid=False` means Gmail no longer recognizes `start_history_id`
        (too old / never seen) — the caller must promote to a full resync
        rather than retry delta.
        """

    @abstractmethod
    async def get_message_metadata(
        self, connected_account_id: uuid.UUID, gmail_message_id: str
    ) -> MessageMetadata:
        """Fetch metadata-only message data (`messages.get(format=metadata)`
        shape). Must never fetch or return a full message body."""

    @abstractmethod
    async def list_message_ids(self, connected_account_id: uuid.UUID) -> MessageIdList:
        """Enumerate every message id currently in the mailbox — the input
        to a full resync."""


_active_reader: GmailReaderPort | None = None


def set_reader(reader: GmailReaderPort | None) -> None:
    """Service-locator hook so jobs/service code can call `get_reader()`
    instead of importing a concrete implementation directly, keeping them
    dependent on the abstract port only. Tests call this to inject a
    seeded `FakeGmailReader` before invoking a job handler, and should
    reset to `None` in teardown. Task 4/5 scope has no live wiring — the
    default (first read with nothing set) is a fresh `FakeGmailReader()`.
    """
    global _active_reader
    _active_reader = reader


def get_reader() -> GmailReaderPort:
    global _active_reader
    if _active_reader is None:
        from app.domains.mail_intake.fake_reader import FakeGmailReader

        _active_reader = FakeGmailReader()
    return _active_reader
