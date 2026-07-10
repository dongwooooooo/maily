import uuid
from datetime import datetime, timezone

import pytest

from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import GmailAuthError, GmailReaderPort


def _reader_with_seed() -> tuple[FakeGmailReader, uuid.UUID]:
    reader = FakeGmailReader()
    account_id = uuid.uuid4()
    reader.seed_mailbox(
        account_id,
        messages=[
            FakeMessage(
                gmail_message_id="msg-1",
                gmail_thread_id="thread-1",
                subject="Invoice #4821",
                sender="billing@example.com",
                snippet="Your invoice for July is attached...",
                label_ids=["INBOX", "UNREAD"],
                received_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        ],
        history_id=100,
    )
    return reader, account_id


async def test_deterministic_history_pages() -> None:
    reader, account_id = _reader_with_seed()
    reader.push_history(
        account_id,
        record_type="message_added",
        message=FakeMessage(
            gmail_message_id="msg-2", gmail_thread_id="thread-2", subject="Standup notes"
        ),
    )

    first = await reader.history(account_id, 100)
    second = await reader.history(account_id, 100)

    assert first == second
    assert [r["gmail_message_id"] for r in first["records"]] == ["msg-2"]
    assert first["valid"] is True
    assert first["new_history_id"] == 101


async def test_gmail_state_snapshot() -> None:
    reader, account_id = _reader_with_seed()

    listing = await reader.list_message_ids(account_id)
    metadata = await reader.get_message_metadata(account_id, "msg-1")
    registration = await reader.register_watch(account_id)

    assert listing["gmail_message_id"] == ["msg-1"]
    assert listing["history_id"] == 100
    assert metadata["subject"] == "Invoice #4821"
    assert metadata["sender"] == "billing@example.com"
    assert metadata["thread_id"] == "thread-1"
    assert metadata["label_ids"] == ["INBOX", "UNREAD"]
    assert registration["topic_name"]
    assert registration["history_id"] == 100


async def test_reader_never_returns_raw_body() -> None:
    reader, account_id = _reader_with_seed()
    metadata = await reader.get_message_metadata(account_id, "msg-1")

    assert "body" not in metadata
    assert set(metadata.keys()) == {
        "subject",
        "sender",
        "snippet",
        "thread_id",
        "label_ids",
        "is_read",
        "is_archived",
        "received_at",
    }
    # port 자체에는 구조적으로 body-fetching method가 없다. 이 port를 구현하는
    # live_reader는 format=full을 호출할 수 없다. 그런 값을 받을 shape의 method가 없기
    # 때문이다.
    assert not hasattr(GmailReaderPort, "get_full_body")
    assert not hasattr(GmailReaderPort, "get_message_body")
    assert not hasattr(GmailReaderPort, "get_body")


async def test_history_reports_invalid_when_start_history_id_too_old() -> None:
    reader, account_id = _reader_with_seed()
    reader.expire_history_before(account_id, 150)

    result = await reader.history(account_id, 100)

    assert result["valid"] is False
    assert result["records"] == []


async def test_history_reports_invalid_for_none_start_history_id() -> None:
    reader, account_id = _reader_with_seed()

    result = await reader.history(account_id, None)

    assert result["valid"] is False


async def test_auth_failure_raises_gmail_auth_error_on_every_method() -> None:
    reader, account_id = _reader_with_seed()
    reader.set_auth_failure(account_id)

    with pytest.raises(GmailAuthError):
        await reader.history(account_id, 100)
    with pytest.raises(GmailAuthError):
        await reader.get_message_metadata(account_id, "msg-1")
    with pytest.raises(GmailAuthError):
        await reader.list_message_ids(account_id)
    with pytest.raises(GmailAuthError):
        await reader.register_watch(account_id)


async def test_labels_added_and_removed_update_read_and_archived_flags() -> None:
    reader, account_id = _reader_with_seed()

    reader.push_history(
        account_id, record_type="labels_removed", gmail_message_id="msg-1", label_ids=["UNREAD"]
    )
    metadata = await reader.get_message_metadata(account_id, "msg-1")
    assert metadata["is_read"] is True
    assert "UNREAD" not in metadata["label_ids"]

    reader.push_history(
        account_id, record_type="labels_removed", gmail_message_id="msg-1", label_ids=["INBOX"]
    )
    metadata = await reader.get_message_metadata(account_id, "msg-1")
    assert metadata["is_archived"] is True
