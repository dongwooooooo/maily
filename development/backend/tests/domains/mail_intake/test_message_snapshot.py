from datetime import datetime, timezone

from sqlalchemy import inspect, select

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.mail_intake import service
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_intake.models import gmail_message_labels, gmail_messages, message_excerpts
from tests.domains.mail_intake.conftest import seed_connected_account, seed_workspace


async def test_gmail_messages_has_no_body_column() -> None:
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("gmail_messages")}
        )
    assert "body" not in columns
    assert "raw_body" not in columns
    assert "excerpt_text" not in columns


async def test_snapshot_upsert_keyed_by_account_and_message() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(
        account_id,
        messages=[
            FakeMessage(
                gmail_message_id="msg-1",
                gmail_thread_id="thread-1",
                subject="Weekly digest",
                sender="digest@example.com",
                snippet="Here is your weekly digest for the team...",
                label_ids=["INBOX", "UNREAD"],
                received_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        ],
        history_id=10,
    )
    set_reader(reader)

    async with engine.begin() as connection:
        result = await service.sync_full(
            connection, connected_account_id=account_id, reason="initial"
        )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["gmail_message_id"] == "msg-1"
    assert rows[0]["subject"] == "Weekly digest"
    assert rows[0]["snapshot_version"] == 0
    assert len(result["message_ids"]) == 1

    # 같은 upstream data로 재실행: idempotent — 중복 row, version bump,
    # 새 changed message_ids가 없다.
    async with engine.begin() as connection:
        second_result = await service.sync_full(
            connection, connected_account_id=account_id, reason="manual"
        )

    async with engine.connect() as connection:
        rows_after = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().all()

    assert len(rows_after) == 1
    assert rows_after[0]["snapshot_version"] == 0
    assert second_result["message_ids"] == []


async def test_excerpt_rejects_raw_body() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(
        account_id,
        messages=[
            FakeMessage(
                gmail_message_id="msg-1",
                gmail_thread_id="thread-1",
                snippet="Short preview only, not the full message body",
            ),
        ],
        history_id=1,
    )
    set_reader(reader)

    async with engine.begin() as connection:
        await service.sync_full(connection, connected_account_id=account_id, reason="initial")

    async with engine.connect() as connection:
        message_row = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().first()
        excerpt_row = (
            await connection.execute(
                select(message_excerpts).where(message_excerpts.c.message_id == message_row["id"])
            )
        ).mappings().first()

    assert excerpt_row is not None
    assert excerpt_row["excerpt_text"] == "Short preview only, not the full message body"
    # message_excerpts는 완전히 별도 table이다. gmail_messages는 Gmail 자체의 짧은
    # `snippet` field만 보관하고 body/excerpt column은 절대 두지 않는다.
    assert message_row["snippet"] == "Short preview only, not the full message body"


async def test_snapshot_changed_event_payload() -> None:
    workspace_id = await seed_workspace()
    account_id = await seed_connected_account(workspace_id=workspace_id)
    reader = FakeGmailReader()
    reader.seed_mailbox(
        account_id,
        messages=[FakeMessage(gmail_message_id="msg-1", gmail_thread_id="thread-1")],
        history_id=5,
    )
    set_reader(reader)

    async with engine.begin() as connection:
        result = await service.sync_full(
            connection, connected_account_id=account_id, reason="initial"
        )

    key = f"source:{account_id}:snapshot:{result['sync_run_id']}"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()

    assert row is not None
    assert row["event_type"] == "gmail_snapshot_changed"
    assert row["producer_domain"] == "mail_intake"
    assert row["payload"]["source_id"] == str(account_id)
    assert row["payload"]["workspace_id"] == str(workspace_id)
    assert row["payload"]["sync_run_id"] == str(result["sync_run_id"])
    assert row["payload"]["message_ids"] == [str(m) for m in result["message_ids"]]


async def test_no_event_when_full_sync_has_no_changes() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(account_id, messages=[], history_id=1)
    set_reader(reader)

    async with engine.begin() as connection:
        result = await service.sync_full(
            connection, connected_account_id=account_id, reason="initial"
        )

    assert result["message_ids"] == []
    key = f"source:{account_id}:snapshot:{result['sync_run_id']}"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()
    assert row is None


async def test_delta_reflects_message_added_deleted_label_added_removed() -> None:
    account_id = await seed_connected_account()
    reader = FakeGmailReader()
    reader.seed_mailbox(
        account_id,
        messages=[
            FakeMessage(
                gmail_message_id="msg-1", gmail_thread_id="thread-1", label_ids=["INBOX", "UNREAD"]
            ),
            FakeMessage(
                gmail_message_id="msg-2", gmail_thread_id="thread-2", label_ids=["INBOX", "UNREAD"]
            ),
        ],
        history_id=10,
    )
    set_reader(reader)
    async with engine.begin() as connection:
        await service.sync_full(connection, connected_account_id=account_id, reason="initial")

    reader.push_history(
        account_id,
        record_type="message_added",
        message=FakeMessage(
            gmail_message_id="msg-3", gmail_thread_id="thread-3", label_ids=["INBOX"]
        ),
    )
    reader.push_history(account_id, record_type="message_deleted", gmail_message_id="msg-2")
    reader.push_history(
        account_id, record_type="labels_removed", gmail_message_id="msg-1", label_ids=["UNREAD"]
    )

    async with engine.begin() as connection:
        result = await service.sync_delta(
            connection, connected_account_id=account_id, start_history_id=10, trigger="notification"
        )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(gmail_messages).where(gmail_messages.c.connected_account_id == account_id)
            )
        ).mappings().all()
        by_gmail_id = {r["gmail_message_id"]: r for r in rows}

    assert set(by_gmail_id.keys()) == {"msg-1", "msg-3"}
    assert by_gmail_id["msg-1"]["is_read"] is True
    assert len(result["message_ids"]) == 3

    async with engine.connect() as connection:
        label_rows = (
            await connection.execute(
                select(gmail_message_labels).where(
                    gmail_message_labels.c.message_id == by_gmail_id["msg-1"]["id"]
                )
            )
        ).mappings().all()
    assert {row["gmail_label_id"] for row in label_rows} == {"INBOX"}
