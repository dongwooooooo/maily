import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ConflictError, ExternalServiceError, NotFoundError
from app.domains.mail_intake import events, repository
from app.domains.mail_intake.gmail_reader import GmailAuthError, get_reader
from app.domains.mail_sources import repository as mail_sources_repository

logger = structlog.get_logger()

_INACTIVE_STATUSES = ("disconnecting", "disconnected")


async def _load_active_account(connection: AsyncConnection, *, connected_account_id: uuid.UUID) -> dict:
    account = await mail_sources_repository.get_connected_account(
        connection, connected_account_id=connected_account_id
    )
    if account is None:
        raise NotFoundError("connected gmail source not found")
    if account["status"] in _INACTIVE_STATUSES:
        raise ConflictError("gmail source is disconnecting or disconnected")
    return account


async def _fail_sync_run_and_emit_recovery(
    connection: AsyncConnection,
    *,
    sync_run_id: uuid.UUID,
    connected_account_id: uuid.UUID,
    account_version: int,
    reason: str,
) -> None:
    await repository.finish_sync_run(
        connection,
        sync_run_id=sync_run_id,
        status="failed",
        finished_at=datetime.now(timezone.utc),
        messages_changed_count=0,
        error_reason=reason,
    )
    await events.publish_recovery_needed(
        connection, connected_account_id=connected_account_id, reason=reason, version=account_version
    )


# --- sync_gmail_full -------------------------------------------------------


async def sync_full(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID, reason: str
) -> dict:
    structlog.contextvars.bind_contextvars(source_id=str(connected_account_id))
    account = await _load_active_account(connection, connected_account_id=connected_account_id)

    reader = get_reader()
    sync_run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    await repository.insert_sync_run(
        connection,
        sync_run_id=sync_run_id,
        connected_account_id=connected_account_id,
        run_type="full",
        trigger=reason,
        status="running",
        started_at=started_at,
    )

    try:
        listing = await reader.list_message_ids(connected_account_id)
    except GmailAuthError as exc:
        await _fail_sync_run_and_emit_recovery(
            connection,
            sync_run_id=sync_run_id,
            connected_account_id=connected_account_id,
            account_version=account["version"],
            reason=exc.reason,
        )
        raise

    changed_message_ids: list[uuid.UUID] = []
    try:
        for gmail_message_id in listing["gmail_message_id"]:
            metadata = await reader.get_message_metadata(connected_account_id, gmail_message_id)
            message_id, changed = await repository.upsert_message_snapshot(
                connection,
                connected_account_id=connected_account_id,
                gmail_message_id=gmail_message_id,
                gmail_thread_id=metadata["thread_id"],
                subject=metadata["subject"],
                sender=metadata["sender"],
                snippet=metadata["snippet"],
                received_at=metadata["received_at"],
                is_read=metadata["is_read"],
                is_archived=metadata["is_archived"],
                last_history_id=listing["history_id"],
            )
            await repository.replace_message_labels(
                connection,
                message_id=message_id,
                labels=[(label_id, label_id) for label_id in metadata["label_ids"]],
            )
            if changed:
                changed_message_ids.append(message_id)
    except GmailAuthError as exc:
        await _fail_sync_run_and_emit_recovery(
            connection,
            sync_run_id=sync_run_id,
            connected_account_id=connected_account_id,
            account_version=account["version"],
            reason=exc.reason,
        )
        raise
    except Exception:
        await repository.finish_sync_run(
            connection,
            sync_run_id=sync_run_id,
            status="failed",
            finished_at=datetime.now(timezone.utc),
            messages_changed_count=len(changed_message_ids),
            error_reason="partial_failure",
        )
        raise

    await repository.finish_sync_run(
        connection,
        sync_run_id=sync_run_id,
        status="succeeded",
        finished_at=datetime.now(timezone.utc),
        messages_changed_count=len(changed_message_ids),
    )

    cursor = await repository.get_cursor(connection, connected_account_id=connected_account_id)
    if cursor is None:
        await repository.insert_cursor(
            connection,
            connected_account_id=connected_account_id,
            last_history_id=listing["history_id"],
            watch_expiration_at=None,
        )
    await repository.advance_cursor(
        connection, connected_account_id=connected_account_id, last_history_id=listing["history_id"]
    )

    await events.publish_snapshot_changed(
        connection,
        connected_account_id=connected_account_id,
        workspace_id=account["workspace_id"],
        sync_run_id=sync_run_id,
        message_ids=changed_message_ids,
    )
    logger.info("Gmail 전체 동기화 완료", messages_changed=len(changed_message_ids))
    return {"sync_run_id": sync_run_id, "message_ids": changed_message_ids}


# --- sync_gmail_delta -------------------------------------------------------


async def _apply_history_record(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    record: dict,
    reader,
    last_history_id: int,
) -> uuid.UUID | None:
    record_type = record["record_type"]
    gmail_message_id = record["gmail_message_id"]

    if record_type == "message_added":
        metadata = await reader.get_message_metadata(connected_account_id, gmail_message_id)
        message_id, changed = await repository.upsert_message_snapshot(
            connection,
            connected_account_id=connected_account_id,
            gmail_message_id=gmail_message_id,
            gmail_thread_id=metadata["thread_id"],
            subject=metadata["subject"],
            sender=metadata["sender"],
            snippet=metadata["snippet"],
            received_at=metadata["received_at"],
            is_read=metadata["is_read"],
            is_archived=metadata["is_archived"],
            last_history_id=last_history_id,
        )
        await repository.replace_message_labels(
            connection,
            message_id=message_id,
            labels=[(label_id, label_id) for label_id in metadata["label_ids"]],
        )
        return message_id if changed else None

    existing = await repository.get_message_by_gmail_id(
        connection, connected_account_id=connected_account_id, gmail_message_id=gmail_message_id
    )
    if existing is None:
        # Not in our snapshot (e.g. never synced) — nothing to reconcile.
        return None

    if record_type == "message_deleted":
        await repository.delete_message_snapshot(connection, message_id=existing["id"])
        return existing["id"]

    if record_type in ("labels_added", "labels_removed"):
        label_ids = record["label_ids"]
        for label_id in label_ids:
            if record_type == "labels_added":
                await repository.add_message_label(
                    connection, message_id=existing["id"], gmail_label_id=label_id
                )
            else:
                await repository.remove_message_label(
                    connection, message_id=existing["id"], gmail_label_id=label_id
                )

        is_read = existing["is_read"]
        is_archived = existing["is_archived"]
        if "UNREAD" in label_ids:
            is_read = record_type == "labels_removed"
        if "INBOX" in label_ids:
            is_archived = record_type == "labels_removed"

        await repository.update_message_state(
            connection,
            message_id=existing["id"],
            is_read=is_read,
            is_archived=is_archived,
            last_history_id=last_history_id,
        )
        return existing["id"]

    raise ExternalServiceError(f"unknown Gmail history record_type: {record_type}")


async def sync_delta(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    start_history_id: int,
    trigger: str,
) -> dict:
    structlog.contextvars.bind_contextvars(source_id=str(connected_account_id))
    account = await mail_sources_repository.get_connected_account(
        connection, connected_account_id=connected_account_id
    )
    if account is None:
        raise NotFoundError("connected gmail source not found")
    if account["status"] in _INACTIVE_STATUSES:
        return {"skipped": True, "reason": "source_inactive"}

    settings_row = await mail_sources_repository.get_source_settings(
        connection, connected_account_id=connected_account_id
    )
    if settings_row is not None and settings_row["paused"]:
        return {"skipped": True, "reason": "paused"}

    cursor = await repository.get_cursor(connection, connected_account_id=connected_account_id)
    if cursor is not None and cursor["cursor_status"] == "invalid":
        result = await sync_full(
            connection, connected_account_id=connected_account_id, reason="cursor_invalid"
        )
        return {"promoted_to_full": True, **result}

    if (
        cursor is not None
        and cursor["last_history_id"] is not None
        and start_history_id < cursor["last_history_id"]
    ):
        # Already-applied region — the caller (e.g. a re-delivered
        # notification) is behind the current cursor.
        return {"noop": True, "message_ids": []}

    reader = get_reader()
    sync_run_id = uuid.uuid4()
    started_at = datetime.now(timezone.utc)
    await repository.insert_sync_run(
        connection,
        sync_run_id=sync_run_id,
        connected_account_id=connected_account_id,
        run_type="delta",
        trigger=trigger,
        status="running",
        started_at=started_at,
    )

    try:
        history_result = await reader.history(connected_account_id, start_history_id)
    except GmailAuthError as exc:
        await _fail_sync_run_and_emit_recovery(
            connection,
            sync_run_id=sync_run_id,
            connected_account_id=connected_account_id,
            account_version=account["version"],
            reason=exc.reason,
        )
        raise

    if not history_result["valid"]:
        await repository.finish_sync_run(
            connection,
            sync_run_id=sync_run_id,
            status="failed",
            finished_at=datetime.now(timezone.utc),
            messages_changed_count=0,
            error_reason="cursor_invalid",
        )
        await repository.mark_cursor_invalid(
            connection, connected_account_id=connected_account_id
        )
        full_result = await sync_full(
            connection, connected_account_id=connected_account_id, reason="cursor_invalid"
        )
        return {"promoted_to_full": True, **full_result}

    changed_message_ids: list[uuid.UUID] = []
    try:
        for record in history_result["records"]:
            changed_id = await _apply_history_record(
                connection,
                connected_account_id=connected_account_id,
                record=record,
                reader=reader,
                last_history_id=history_result["new_history_id"],
            )
            if changed_id is not None:
                changed_message_ids.append(changed_id)
    except GmailAuthError as exc:
        await _fail_sync_run_and_emit_recovery(
            connection,
            sync_run_id=sync_run_id,
            connected_account_id=connected_account_id,
            account_version=account["version"],
            reason=exc.reason,
        )
        raise
    except Exception:
        await repository.finish_sync_run(
            connection,
            sync_run_id=sync_run_id,
            status="failed",
            finished_at=datetime.now(timezone.utc),
            messages_changed_count=len(changed_message_ids),
            error_reason="partial_failure",
        )
        raise

    await repository.finish_sync_run(
        connection,
        sync_run_id=sync_run_id,
        status="succeeded",
        finished_at=datetime.now(timezone.utc),
        messages_changed_count=len(changed_message_ids),
    )
    await repository.advance_cursor(
        connection,
        connected_account_id=connected_account_id,
        last_history_id=history_result["new_history_id"],
    )

    await events.publish_snapshot_changed(
        connection,
        connected_account_id=connected_account_id,
        workspace_id=account["workspace_id"],
        sync_run_id=sync_run_id,
        message_ids=changed_message_ids,
    )
    logger.info("Gmail 증분 동기화 완료", messages_changed=len(changed_message_ids))
    return {"sync_run_id": sync_run_id, "message_ids": changed_message_ids}


# --- process_gmail_notification ---------------------------------------------


async def process_notification(
    connection: AsyncConnection,
    *,
    email_address: str,
    history_id: int,
    notification_id: str | None = None,
) -> dict:
    dedupe_key = f"gmail-notification:{email_address}:{history_id}"
    row_id = uuid.uuid4()
    is_new = True
    try:
        async with connection.begin_nested():
            await repository.insert_notification_event(
                connection,
                notification_id=row_id,
                email_address=email_address,
                history_id=history_id,
                dedupe_key=dedupe_key,
            )
    except IntegrityError:
        is_new = False

    if not is_new:
        logger.info("중복 Pub/Sub 알림 무시", email_address=email_address)
        return {"deduped": True, "queued_source_ids": []}

    await events.publish_notification_received(
        connection, email_address=email_address, history_id=history_id
    )

    sources = await repository.list_active_sources_by_email(connection, email_address=email_address)
    queued_source_ids: list[uuid.UUID] = []
    for source in sources:
        source_id = source["id"]
        job_id = await repository.enqueue_job(
            connection,
            job_type="sync_delta",
            payload={"source_id": str(source_id), "start_history_id": history_id},
            idempotency_key=f"sync-delta:{source_id}:{history_id}",
            lock_key=f"source:{source_id}",
            scheduled_at=datetime.now(timezone.utc),
        )
        if job_id is not None:
            queued_source_ids.append(source_id)

    await repository.mark_notification_processed(connection, notification_id=row_id)
    logger.info(
        "Pub/Sub 알림 처리 완료",
        email_address=email_address,
        queued_source_count=len(queued_source_ids),
    )
    return {"deduped": False, "queued_source_ids": queued_source_ids}


# --- register_watch / renew_watch -------------------------------------------


async def register_watch(connection: AsyncConnection, *, connected_account_id: uuid.UUID) -> dict:
    structlog.contextvars.bind_contextvars(source_id=str(connected_account_id))
    account = await mail_sources_repository.get_connected_account(
        connection, connected_account_id=connected_account_id
    )
    if account is None:
        raise NotFoundError("connected gmail source not found")
    if account["status"] in _INACTIVE_STATUSES:
        return {"skipped": True, "reason": "source_inactive"}

    reader = get_reader()
    try:
        registration = await reader.register_watch(connected_account_id)
    except GmailAuthError as exc:
        await events.publish_recovery_needed(
            connection,
            connected_account_id=connected_account_id,
            reason=exc.reason,
            version=account["version"],
        )
        raise

    existing_registration = await repository.get_watch_registration(
        connection, connected_account_id=connected_account_id
    )
    if existing_registration is None:
        await repository.insert_watch_registration(
            connection,
            connected_account_id=connected_account_id,
            topic_name=registration["topic_name"],
            expiration=registration["expiration"],
            status="active",
        )
    else:
        await repository.update_watch_registration(
            connection,
            registration_id=existing_registration["id"],
            topic_name=registration["topic_name"],
            expiration=registration["expiration"],
            status="active",
        )

    cursor = await repository.get_cursor(connection, connected_account_id=connected_account_id)
    if cursor is None:
        await repository.insert_cursor(
            connection,
            connected_account_id=connected_account_id,
            last_history_id=registration["history_id"],
            watch_expiration_at=registration["expiration"],
        )
    else:
        await repository.update_watch_expiration(
            connection,
            connected_account_id=connected_account_id,
            watch_expiration_at=registration["expiration"],
        )

    if existing_registration is None:
        # First-ever registration for this source — queue the initial full
        # resync (mail_intake.md "register_watch: watch 등록 + 초기
        # sync_full 큐잉"). A renewal (existing_registration present)
        # never re-triggers this.
        await repository.enqueue_job(
            connection,
            job_type="sync_full",
            payload={"source_id": str(connected_account_id), "reason": "initial"},
            idempotency_key=f"sync-full:{connected_account_id}:initial",
            lock_key=f"source:{connected_account_id}",
            scheduled_at=datetime.now(timezone.utc),
        )

    logger.info("Gmail watch 등록 완료", topic_name=registration["topic_name"])
    return {"topic_name": registration["topic_name"], "expiration": registration["expiration"]}


async def renew_watch(connection: AsyncConnection, *, connected_account_id: uuid.UUID) -> dict:
    account = await mail_sources_repository.get_connected_account(
        connection, connected_account_id=connected_account_id
    )
    if account is None:
        raise NotFoundError("connected gmail source not found")
    if account["status"] in ("disconnecting", "disconnected", "paused"):
        return {"skipped": True, "reason": "source_inactive"}
    return await register_watch(connection, connected_account_id=connected_account_id)


# --- poll_history (fallback) -------------------------------------------------


async def poll_history(connection: AsyncConnection, *, connected_account_id: uuid.UUID) -> dict:
    structlog.contextvars.bind_contextvars(source_id=str(connected_account_id))
    account = await mail_sources_repository.get_connected_account(
        connection, connected_account_id=connected_account_id
    )
    if account is None:
        raise NotFoundError("connected gmail source not found")
    if account["status"] in _INACTIVE_STATUSES:
        return {"skipped": True, "reason": "source_inactive"}

    settings_row = await mail_sources_repository.get_source_settings(
        connection, connected_account_id=connected_account_id
    )
    if settings_row is not None and settings_row["paused"]:
        return {"skipped": True, "reason": "paused"}

    cursor = await repository.get_cursor(connection, connected_account_id=connected_account_id)
    if cursor is None:
        return {"skipped": True, "reason": "no_cursor"}

    now = datetime.now(timezone.utc)
    if cursor["cursor_status"] == "invalid":
        job_id = await repository.enqueue_job(
            connection,
            job_type="sync_full",
            payload={"source_id": str(connected_account_id), "reason": "cursor_invalid"},
            idempotency_key=f"sync-full:{connected_account_id}:cursor-invalid",
            lock_key=f"source:{connected_account_id}",
            scheduled_at=now,
        )
        return {"queued_full": job_id is not None}

    reader = get_reader()
    try:
        history_result = await reader.history(connected_account_id, cursor["last_history_id"])
    except GmailAuthError as exc:
        await events.publish_recovery_needed(
            connection,
            connected_account_id=connected_account_id,
            reason=exc.reason,
            version=account["version"],
        )
        raise

    if not history_result["valid"]:
        await repository.mark_cursor_invalid(
            connection, connected_account_id=connected_account_id
        )
        job_id = await repository.enqueue_job(
            connection,
            job_type="sync_full",
            payload={"source_id": str(connected_account_id), "reason": "cursor_invalid"},
            idempotency_key=f"sync-full:{connected_account_id}:cursor-invalid",
            lock_key=f"source:{connected_account_id}",
            scheduled_at=now,
        )
        return {"queued_full": job_id is not None}

    if history_result["records"]:
        job_id = await repository.enqueue_job(
            connection,
            job_type="sync_delta",
            payload={
                "source_id": str(connected_account_id),
                "start_history_id": cursor["last_history_id"],
            },
            idempotency_key=f"sync-delta:{connected_account_id}:{cursor['last_history_id']}",
            lock_key=f"source:{connected_account_id}",
            scheduled_at=now,
        )
        return {"queued_delta": job_id is not None}

    await repository.touch_last_successful_sync(
        connection, connected_account_id=connected_account_id
    )
    return {"noop": True}


def default_polling_staleness_threshold() -> datetime:
    """POC default: sources not successfully synced in the last 10 minutes
    are polling targets. No operational tuning data exists yet — this is a
    conservative placeholder, not a product-confirmed SLA."""
    return datetime.now(timezone.utc) - timedelta(minutes=10)


def default_watch_renewal_threshold() -> datetime:
    """POC default: watches expiring within 24h are renewal targets — well
    inside Gmail's 7-day watch lifetime, matching mail_intake.md "watch
    만료 임박(7일 이내)" with margin for a daily renewal scheduler."""
    return datetime.now(timezone.utc) + timedelta(hours=24)
