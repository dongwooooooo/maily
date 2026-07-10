import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.jobs.models import job_runs
from app.domains.mail_intake.models import (
    gmail_message_labels,
    gmail_messages,
    gmail_notification_events,
    gmail_sync_cursors,
    gmail_watch_registrations,
    message_excerpts,
    sync_runs,
)
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings

# --- job_runs enqueue helper (이 domain의 모든 job이 공유) ------------------


async def enqueue_job(
    connection: AsyncConnection,
    *,
    job_type: str,
    payload: dict,
    idempotency_key: str,
    lock_key: str | None,
    scheduled_at: datetime,
) -> uuid.UUID | None:
    """job_runs row 하나를 insert하고 (job_type, idempotency_key)로 dedupe한다.

    새 row id를 반환한다. 해당 key의 row가 이미 있으면 None을 반환한다(duplicate enqueue는
    no-op). core.outbox.append_event와 같은 패턴이다.
    """
    stmt = (
        pg_insert(job_runs)
        .values(
            id=uuid.uuid4(),
            job_type=job_type,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=lock_key,
            scheduled_at=scheduled_at,
        )
        .on_conflict_do_nothing(constraint="uq_job_runs_job_type_idempotency_key")
        .returning(job_runs.c.id)
    )
    result = await connection.execute(stmt)
    row = result.first()
    return row.id if row is not None else None


# --- message snapshot 관리 -----------------------------------------------


async def _upsert_excerpt(
    connection: AsyncConnection, *, message_id: uuid.UUID, excerpt_text: str
) -> None:
    now = datetime.now(timezone.utc)
    existing = (
        await connection.execute(
            select(message_excerpts.c.id).where(message_excerpts.c.message_id == message_id)
        )
    ).first()
    if existing is None:
        await connection.execute(
            insert(message_excerpts).values(
                id=uuid.uuid4(), message_id=message_id, excerpt_text=excerpt_text, updated_at=now
            )
        )
    else:
        await connection.execute(
            update(message_excerpts)
            .where(message_excerpts.c.message_id == message_id)
            .values(excerpt_text=excerpt_text, updated_at=now)
        )


async def upsert_message_snapshot(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    gmail_message_id: str,
    gmail_thread_id: str,
    subject: str | None,
    sender: str | None,
    snippet: str | None,
    received_at: datetime | None,
    is_read: bool,
    is_archived: bool,
    last_history_id: int | None,
) -> tuple[uuid.UUID, bool]:
    """Gmail message snapshot row 하나를 upsert한다.

    key는 (connected_account_id, gmail_message_id)다. (message_id, changed)를 반환한다.
    changed=False는 모든 field가 기존 row와 이미 일치한다는 뜻이다. snapshot_version은 건드리지
    않고, caller는 이 message_id를 gmail_snapshot_changed event에 포함하면 안 된다
    (mail_intake.md "이미 최신인 메시지는 snapshot_version 증가 없이 no-op"). excerpt(Gmail의
    snippet이며 raw body가 아님)는 실제 change와 함께 별도 message_excerpts table에 upsert된다.
    """
    existing = (
        await connection.execute(
            select(gmail_messages).where(
                gmail_messages.c.connected_account_id == connected_account_id,
                gmail_messages.c.gmail_message_id == gmail_message_id,
            )
        )
    ).mappings().first()

    if existing is None:
        message_id = uuid.uuid4()
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=connected_account_id,
                gmail_message_id=gmail_message_id,
                gmail_thread_id=gmail_thread_id,
                subject=subject,
                sender=sender,
                snippet=snippet,
                received_at=received_at,
                is_read=is_read,
                is_archived=is_archived,
                last_history_id=last_history_id,
                snapshot_version=0,
            )
        )
        await _upsert_excerpt(connection, message_id=message_id, excerpt_text=snippet or "")
        return message_id, True

    unchanged = (
        existing["gmail_thread_id"] == gmail_thread_id
        and existing["subject"] == subject
        and existing["sender"] == sender
        and existing["snippet"] == snippet
        and existing["received_at"] == received_at
        and existing["is_read"] == is_read
        and existing["is_archived"] == is_archived
    )
    if unchanged:
        return existing["id"], False

    await connection.execute(
        update(gmail_messages)
        .where(gmail_messages.c.id == existing["id"])
        .values(
            gmail_thread_id=gmail_thread_id,
            subject=subject,
            sender=sender,
            snippet=snippet,
            received_at=received_at,
            is_read=is_read,
            is_archived=is_archived,
            last_history_id=last_history_id,
            snapshot_version=existing["snapshot_version"] + 1,
        )
    )
    await _upsert_excerpt(connection, message_id=existing["id"], excerpt_text=snippet or "")
    return existing["id"], True


async def get_message_by_gmail_id(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID, gmail_message_id: str
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_messages).where(
                gmail_messages.c.connected_account_id == connected_account_id,
                gmail_messages.c.gmail_message_id == gmail_message_id,
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_message(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_excerpt(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(
            select(message_excerpts).where(message_excerpts.c.message_id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_message_labels(connection: AsyncConnection, *, message_id: uuid.UUID) -> list[dict]:
    rows = (
        await connection.execute(
            select(gmail_message_labels).where(gmail_message_labels.c.message_id == message_id)
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def replace_message_labels(
    connection: AsyncConnection, *, message_id: uuid.UUID, labels: list[tuple[str, str]]
) -> None:
    """full replace.

    full sync에서 사용한다. 이때 reader의 message별 label_ids는 해당 message에 대한 완전하고
    authoritative한 snapshot이다.
    """
    await connection.execute(
        delete(gmail_message_labels).where(gmail_message_labels.c.message_id == message_id)
    )
    if labels:
        await connection.execute(
            insert(gmail_message_labels),
            [
                {
                    "id": uuid.uuid4(),
                    "message_id": message_id,
                    "gmail_label_id": gmail_label_id,
                    "label_name": label_name,
                }
                for gmail_label_id, label_name in labels
            ],
        )


async def add_message_label(
    connection: AsyncConnection, *, message_id: uuid.UUID, gmail_label_id: str
) -> None:
    existing = (
        await connection.execute(
            select(gmail_message_labels.c.id).where(
                gmail_message_labels.c.message_id == message_id,
                gmail_message_labels.c.gmail_label_id == gmail_label_id,
            )
        )
    ).first()
    if existing is None:
        await connection.execute(
            insert(gmail_message_labels).values(
                id=uuid.uuid4(),
                message_id=message_id,
                gmail_label_id=gmail_label_id,
                label_name=gmail_label_id,
            )
        )


async def remove_message_label(
    connection: AsyncConnection, *, message_id: uuid.UUID, gmail_label_id: str
) -> None:
    await connection.execute(
        delete(gmail_message_labels).where(
            gmail_message_labels.c.message_id == message_id,
            gmail_message_labels.c.gmail_label_id == gmail_label_id,
        )
    )


async def update_message_state(
    connection: AsyncConnection,
    *,
    message_id: uuid.UUID,
    is_read: bool,
    is_archived: bool,
    last_history_id: int | None,
) -> None:
    row = (
        await connection.execute(
            select(gmail_messages.c.snapshot_version).where(gmail_messages.c.id == message_id)
        )
    ).first()
    next_version = (row[0] + 1) if row is not None else 0
    await connection.execute(
        update(gmail_messages)
        .where(gmail_messages.c.id == message_id)
        .values(
            is_read=is_read,
            is_archived=is_archived,
            last_history_id=last_history_id,
            snapshot_version=next_version,
        )
    )


async def delete_message_snapshot(connection: AsyncConnection, *, message_id: uuid.UUID) -> None:
    """Gmail이 messagesDeleted를 보고했다.

    db-schema.md에는 gmail_messages용 soft-delete column이 없고, snapshot은 완전히
    rebuildable/non-authoritative하다고 문서화되어 있다. 따라서 tombstone을 남기지 않고 row와
    child(labels, excerpt)를 hard-delete한다.
    """
    await connection.execute(
        delete(gmail_message_labels).where(gmail_message_labels.c.message_id == message_id)
    )
    await connection.execute(
        delete(message_excerpts).where(message_excerpts.c.message_id == message_id)
    )
    await connection.execute(delete(gmail_messages).where(gmail_messages.c.id == message_id))


# --- sync cursor 관리 -----------------------------------------------------


async def get_cursor(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_sync_cursors).where(
                gmail_sync_cursors.c.connected_account_id == connected_account_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def insert_cursor(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    last_history_id: int | None,
    watch_expiration_at: datetime | None,
) -> None:
    await connection.execute(
        insert(gmail_sync_cursors).values(
            id=uuid.uuid4(),
            connected_account_id=connected_account_id,
            last_history_id=last_history_id,
            watch_expiration_at=watch_expiration_at,
            cursor_status="valid",
        )
    )


async def update_watch_expiration(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    watch_expiration_at: datetime,
) -> None:
    await connection.execute(
        update(gmail_sync_cursors)
        .where(gmail_sync_cursors.c.connected_account_id == connected_account_id)
        .values(watch_expiration_at=watch_expiration_at)
    )


async def advance_cursor(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    last_history_id: int,
) -> None:
    await connection.execute(
        update(gmail_sync_cursors)
        .where(gmail_sync_cursors.c.connected_account_id == connected_account_id)
        .values(
            last_history_id=last_history_id,
            last_successful_sync_at=datetime.now(timezone.utc),
            cursor_status="valid",
        )
    )


async def mark_cursor_invalid(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> None:
    await connection.execute(
        update(gmail_sync_cursors)
        .where(gmail_sync_cursors.c.connected_account_id == connected_account_id)
        .values(cursor_status="invalid")
    )


async def touch_last_successful_sync(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> None:
    await connection.execute(
        update(gmail_sync_cursors)
        .where(gmail_sync_cursors.c.connected_account_id == connected_account_id)
        .values(last_successful_sync_at=datetime.now(timezone.utc))
    )


_INACTIVE_STATUSES = ("disconnecting", "disconnected", "paused")


async def list_sources_for_polling(
    connection: AsyncConnection, *, stale_before: datetime
) -> list[dict]:
    """fallback-polling target selection.

    active, unpaused source 중 cursor의 last_successful_sync_at이 null이거나 `stale_before`보다
    오래된 source를 고른다(mail_intake.md poll_history
    "[데이터경계] 대상 선정은 활성·미paused source로 한정").
    """
    rows = (
        await connection.execute(
            select(
                gmail_sync_cursors.c.connected_account_id,
                gmail_sync_cursors.c.last_history_id,
                gmail_sync_cursors.c.cursor_status,
                gmail_sync_cursors.c.last_successful_sync_at,
            )
            .select_from(
                gmail_sync_cursors.join(
                    connected_gmail_accounts,
                    connected_gmail_accounts.c.id == gmail_sync_cursors.c.connected_account_id,
                ).join(
                    gmail_source_settings,
                    gmail_source_settings.c.connected_account_id
                    == connected_gmail_accounts.c.id,
                )
            )
            .where(
                connected_gmail_accounts.c.status.notin_(_INACTIVE_STATUSES),
                gmail_source_settings.c.paused.is_(False),
                (gmail_sync_cursors.c.last_successful_sync_at.is_(None))
                | (gmail_sync_cursors.c.last_successful_sync_at < stale_before),
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# --- watch registration 관리 -----------------------------------------------


async def get_watch_registration(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_watch_registrations)
            .where(gmail_watch_registrations.c.connected_account_id == connected_account_id)
            .order_by(gmail_watch_registrations.c.expiration.desc())
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def insert_watch_registration(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    topic_name: str,
    expiration: datetime,
    status: str,
) -> uuid.UUID:
    registration_id = uuid.uuid4()
    await connection.execute(
        insert(gmail_watch_registrations).values(
            id=registration_id,
            connected_account_id=connected_account_id,
            topic_name=topic_name,
            expiration=expiration,
            status=status,
        )
    )
    return registration_id


async def update_watch_registration(
    connection: AsyncConnection,
    *,
    registration_id: uuid.UUID,
    topic_name: str,
    expiration: datetime,
    status: str,
) -> None:
    await connection.execute(
        update(gmail_watch_registrations)
        .where(gmail_watch_registrations.c.id == registration_id)
        .values(topic_name=topic_name, expiration=expiration, status=status)
    )


async def mark_watch_registration_failed(
    connection: AsyncConnection, *, registration_id: uuid.UUID
) -> None:
    await connection.execute(
        update(gmail_watch_registrations)
        .where(gmail_watch_registrations.c.id == registration_id)
        .values(status="failed")
    )


async def list_watches_expiring_before(
    connection: AsyncConnection, *, before: datetime
) -> list[dict]:
    """renewal target selection.

    `before` 전에 expiring되는 active watch 중 아직 sync eligible한 source로 제한한다
    (mail_intake.md renew_watch "[선행조건] disconnecting/paused/credential revoked → 갱신 스킵").
    """
    rows = (
        await connection.execute(
            select(
                gmail_watch_registrations.c.id,
                gmail_watch_registrations.c.connected_account_id,
                gmail_watch_registrations.c.expiration,
            )
            .select_from(
                gmail_watch_registrations.join(
                    connected_gmail_accounts,
                    connected_gmail_accounts.c.id
                    == gmail_watch_registrations.c.connected_account_id,
                )
            )
            .where(
                gmail_watch_registrations.c.status == "active",
                gmail_watch_registrations.c.expiration < before,
                connected_gmail_accounts.c.status.notin_(_INACTIVE_STATUSES),
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# --- notification event 관리 ------------------------------------------------


async def insert_notification_event(
    connection: AsyncConnection,
    *,
    notification_id: uuid.UUID,
    email_address: str,
    history_id: int,
    dedupe_key: str,
) -> None:
    """duplicate dedupe_key면 sqlalchemy.exc.IntegrityError를 raise한다.

    caller는 이를 nested transaction으로 감싸고 already-processed notification으로 취급한다
    (mail_intake.md "UNIQUE가 두 번째 insert 거부(IntegrityError)").
    """
    await connection.execute(
        insert(gmail_notification_events).values(
            id=notification_id,
            email_address=email_address,
            history_id=history_id,
            dedupe_key=dedupe_key,
        )
    )


async def mark_notification_processed(
    connection: AsyncConnection, *, notification_id: uuid.UUID
) -> None:
    await connection.execute(
        update(gmail_notification_events)
        .where(gmail_notification_events.c.id == notification_id)
        .values(processed_at=datetime.now(timezone.utc))
    )


async def get_notification_event_by_dedupe_key(
    connection: AsyncConnection, *, dedupe_key: str
) -> dict | None:
    row = (
        await connection.execute(
            select(gmail_notification_events).where(
                gmail_notification_events.c.dedupe_key == dedupe_key
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def list_active_sources_by_email(
    connection: AsyncConnection, *, email_address: str
) -> list[dict]:
    """process_gmail_notification의 fan-out target selection.

    모든 workspace에 걸쳐 이 Gmail address를 가진 active(disconnecting/disconnected 아님),
    unpaused source를 모두 고른다(module-boundaries.md
    "같은 Gmail 주소가 여러 active connection에 존재하면 ... 전체로 fan-out").
    """
    rows = (
        await connection.execute(
            select(
                connected_gmail_accounts.c.id,
                connected_gmail_accounts.c.workspace_id,
            )
            .select_from(
                connected_gmail_accounts.join(
                    gmail_source_settings,
                    gmail_source_settings.c.connected_account_id
                    == connected_gmail_accounts.c.id,
                )
            )
            .where(
                connected_gmail_accounts.c.gmail_address == email_address,
                connected_gmail_accounts.c.status.notin_(("disconnecting", "disconnected")),
                gmail_source_settings.c.paused.is_(False),
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# --- sync run 관리 -----------------------------------------------------


async def insert_sync_run(
    connection: AsyncConnection,
    *,
    sync_run_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    run_type: str,
    trigger: str,
    status: str,
    started_at: datetime,
) -> None:
    await connection.execute(
        insert(sync_runs).values(
            id=sync_run_id,
            connected_account_id=connected_account_id,
            run_type=run_type,
            trigger=trigger,
            status=status,
            started_at=started_at,
        )
    )


async def finish_sync_run(
    connection: AsyncConnection,
    *,
    sync_run_id: uuid.UUID,
    status: str,
    finished_at: datetime,
    messages_changed_count: int,
    error_reason: str | None = None,
) -> None:
    await connection.execute(
        update(sync_runs)
        .where(sync_runs.c.id == sync_run_id)
        .values(
            status=status,
            finished_at=finished_at,
            messages_changed_count=messages_changed_count,
            error_reason=error_reason,
        )
    )


async def get_sync_run(connection: AsyncConnection, *, sync_run_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(select(sync_runs).where(sync_runs.c.id == sync_run_id))
    ).mappings().first()
    return dict(row) if row is not None else None
