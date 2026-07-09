"""Deterministic in-memory GmailReaderPort double for TDD.

Task 4/5 primary deliverable: no live Gmail credential is needed to test
watch registration, history delta, message metadata reads, or full
enumeration. Seed a mailbox with `seed_mailbox`, then feed changes with
`push_history`. Same seed -> same responses across repeated calls; there is
no hidden randomness and no clock read inside response bodies other than
what `register_watch` computes for `expiration` (kept short and documented
below since Gmail's own expiration is itself a relative-to-now value).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.domains.mail_intake.gmail_reader import (
    GmailAuthError,
    GmailReaderPort,
    HistoryResult,
    MessageIdList,
    MessageMetadata,
    WatchRegistration,
)


@dataclass
class FakeMessage:
    gmail_message_id: str
    gmail_thread_id: str
    subject: str | None = None
    sender: str | None = None
    snippet: str | None = None
    label_ids: list[str] = field(default_factory=lambda: ["INBOX", "UNREAD"])
    is_read: bool = False
    is_archived: bool = False
    received_at: datetime | None = None


@dataclass
class _Mailbox:
    messages: dict[str, FakeMessage] = field(default_factory=dict)
    history_records: list[dict] = field(default_factory=list)
    current_history_id: int = 1
    oldest_known_history_id: int = 1
    watch_topic: str = "projects/maily-fake/topics/gmail-fake"
    watch_expiration_days: int = 7
    auth_failure: bool = False


class FakeGmailReader(GmailReaderPort):
    def __init__(self) -> None:
        self._mailboxes: dict[uuid.UUID, _Mailbox] = {}

    # --- seeding / test control -------------------------------------------------

    def seed_mailbox(
        self,
        connected_account_id: uuid.UUID,
        *,
        messages: list[FakeMessage] | None = None,
        history_id: int = 1,
    ) -> None:
        self._mailboxes[connected_account_id] = _Mailbox(
            messages={m.gmail_message_id: m for m in (messages or [])},
            current_history_id=history_id,
            oldest_known_history_id=history_id,
        )

    def set_auth_failure(self, connected_account_id: uuid.UUID, *, failing: bool = True) -> None:
        self._get_mailbox(connected_account_id).auth_failure = failing

    def expire_history_before(
        self, connected_account_id: uuid.UUID, oldest_known_history_id: int
    ) -> None:
        """Simulate Gmail forgetting history older than this point — a
        `history(start_history_id)` call with a smaller value now returns
        `valid=False`."""
        self._get_mailbox(connected_account_id).oldest_known_history_id = (
            oldest_known_history_id
        )

    def push_history(
        self,
        connected_account_id: uuid.UUID,
        *,
        record_type: str,
        message: FakeMessage | None = None,
        gmail_message_id: str | None = None,
        label_ids: list[str] | None = None,
    ) -> int:
        """Append one history record and advance current_history_id.

        record_type: "message_added" | "message_deleted" | "labels_added" | "labels_removed"
        Returns the new history_id.
        """
        mailbox = self._get_mailbox(connected_account_id)
        mailbox.current_history_id += 1
        history_id = mailbox.current_history_id

        if record_type == "message_added":
            if message is None:
                raise ValueError("message_added requires `message`")
            mailbox.messages[message.gmail_message_id] = message
            target_id = message.gmail_message_id
        elif record_type == "message_deleted":
            if gmail_message_id is None:
                raise ValueError("message_deleted requires `gmail_message_id`")
            target_id = gmail_message_id
            mailbox.messages.pop(target_id, None)
        elif record_type in ("labels_added", "labels_removed"):
            if gmail_message_id is None:
                raise ValueError(f"{record_type} requires `gmail_message_id`")
            target_id = gmail_message_id
            existing = mailbox.messages.get(target_id)
            if existing is not None and label_ids:
                if record_type == "labels_added":
                    existing.label_ids = sorted(set(existing.label_ids) | set(label_ids))
                    if "UNREAD" in label_ids:
                        existing.is_read = False
                    if "INBOX" in label_ids:
                        existing.is_archived = False
                else:
                    existing.label_ids = sorted(set(existing.label_ids) - set(label_ids))
                    if "UNREAD" in label_ids:
                        existing.is_read = True
                    if "INBOX" in label_ids:
                        existing.is_archived = True
        else:
            raise ValueError(f"unknown record_type: {record_type}")

        mailbox.history_records.append(
            {
                "history_id": history_id,
                "record_type": record_type,
                "gmail_message_id": target_id,
                "label_ids": list(label_ids or []),
            }
        )
        return history_id

    def _get_mailbox(self, connected_account_id: uuid.UUID) -> _Mailbox:
        mailbox = self._mailboxes.get(connected_account_id)
        if mailbox is None:
            raise KeyError(f"no fake mailbox seeded for {connected_account_id}")
        return mailbox

    # --- GmailReaderPort ----------------------------------------------------

    async def register_watch(self, connected_account_id: uuid.UUID) -> WatchRegistration:
        mailbox = self._get_mailbox(connected_account_id)
        if mailbox.auth_failure:
            raise GmailAuthError("fake auth failure on register_watch", reason="watch_failed")
        expiration = datetime.now(timezone.utc) + timedelta(days=mailbox.watch_expiration_days)
        return WatchRegistration(
            topic_name=mailbox.watch_topic,
            expiration=expiration,
            history_id=mailbox.current_history_id,
        )

    async def history(
        self, connected_account_id: uuid.UUID, start_history_id: int | None
    ) -> HistoryResult:
        mailbox = self._get_mailbox(connected_account_id)
        if mailbox.auth_failure:
            raise GmailAuthError("fake auth failure on history")

        if start_history_id is None or start_history_id < mailbox.oldest_known_history_id:
            return HistoryResult(
                records=[], new_history_id=mailbox.current_history_id, valid=False
            )

        records: list[dict] = [
            {
                "record_type": r["record_type"],
                "gmail_message_id": r["gmail_message_id"],
                "label_ids": r["label_ids"],
            }
            for r in mailbox.history_records
            if r["history_id"] > start_history_id
        ]
        return HistoryResult(
            records=records, new_history_id=mailbox.current_history_id, valid=True
        )

    async def get_message_metadata(
        self, connected_account_id: uuid.UUID, gmail_message_id: str
    ) -> MessageMetadata:
        mailbox = self._get_mailbox(connected_account_id)
        if mailbox.auth_failure:
            raise GmailAuthError("fake auth failure on get_message_metadata")
        message = mailbox.messages.get(gmail_message_id)
        if message is None:
            raise KeyError(f"no fake message {gmail_message_id}")
        return MessageMetadata(
            subject=message.subject,
            sender=message.sender,
            snippet=message.snippet,
            thread_id=message.gmail_thread_id,
            label_ids=list(message.label_ids),
            is_read=message.is_read,
            is_archived=message.is_archived,
            received_at=message.received_at,
        )

    async def list_message_ids(self, connected_account_id: uuid.UUID) -> MessageIdList:
        mailbox = self._get_mailbox(connected_account_id)
        if mailbox.auth_failure:
            raise GmailAuthError("fake auth failure on list_message_ids")
        return MessageIdList(
            gmail_message_id=sorted(mailbox.messages.keys()),
            history_id=mailbox.current_history_id,
        )
