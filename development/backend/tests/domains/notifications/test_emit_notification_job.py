import uuid

from sqlalchemy import select

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.notifications import service
from app.domains.notifications.jobs.emit_notification import (
    emit_notification_job,
    run_emit_notification,
)
from app.domains.notifications.models import notification_events
from tests.domains.notifications.conftest import seed_scope


def _recovery_payload(workspace_id: uuid.UUID, source_id: uuid.UUID, *, version: int = 0) -> dict:
    return {
        "workspace_id": str(workspace_id),
        "source_id": str(source_id),
        "reason": "auth_error",
        "version": version,
    }


async def test_emit_creates_event_and_outbox() -> None:
    """[정상] 소비 event 도착 -> notification_events insert + outbox
    notification_event_created 1건."""
    workspace_id, _user_id, account_id = await seed_scope()

    async with engine.begin() as connection:
        notification_id = await run_emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload=_recovery_payload(workspace_id, account_id),
        )

    async with engine.connect() as connection:
        event_row = (
            await connection.execute(
                select(notification_events).where(notification_events.c.id == notification_id)
            )
        ).mappings().first()
        outbox_row = (
            await connection.execute(
                select(outbox_events).where(
                    outbox_events.c.idempotency_key == f"notification:{notification_id}:created"
                )
            )
        ).mappings().first()

    assert event_row is not None
    assert event_row["notification_type"] == service.NOTIFICATION_TYPE_RECOVERY_NEEDED
    assert event_row["route_target"] == {"screen": service.SCREEN_ACCOUNT_SETTINGS, "item_id": str(account_id)}
    assert event_row["read_at"] is None

    assert outbox_row is not None
    assert outbox_row["event_type"] == "notification_event_created"
    assert outbox_row["payload"]["notification_id"] == str(notification_id)
    assert outbox_row["payload"]["workspace_id"] == str(workspace_id)


async def test_emit_via_job_handler_entry_point() -> None:
    """JOB_HANDLERS["emit_notification"] callable — __init__.py contract에 따른
    payload shape는 {"trigger": ..., "payload": {...}}이다."""
    workspace_id, _user_id, account_id = await seed_scope()

    await emit_notification_job(
        {
            "trigger": service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            "payload": _recovery_payload(workspace_id, account_id),
        }
    )

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
    assert len(rows) == 1


async def test_emit_idempotent_single_push() -> None:
    """[멱등] 같은 원인 event가 두 번 dispatch -> notification_event 1건,
    outbox notification_event_created 1건(push도 1회)."""
    workspace_id, _user_id, account_id = await seed_scope()
    payload = _recovery_payload(workspace_id, account_id, version=3)

    async with engine.begin() as connection:
        first_id = await run_emit_notification(
            connection, trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED, payload=payload
        )
    async with engine.begin() as connection:
        second_id = await run_emit_notification(
            connection, trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED, payload=payload
        )

    assert first_id == second_id

    async with engine.connect() as connection:
        event_rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
        outbox_rows = (
            await connection.execute(
                select(outbox_events).where(
                    outbox_events.c.idempotency_key == f"notification:{first_id}:created"
                )
            )
        ).mappings().all()

    assert len(event_rows) == 1
    assert len(outbox_rows) == 1


async def test_emit_different_reason_is_a_separate_notification() -> None:
    """[멱등] 원인(reason)이 바뀌면 별개 알림 — dedupe는 원인 단위."""
    workspace_id, _user_id, account_id = await seed_scope()

    async with engine.begin() as connection:
        first_id = await run_emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_id),
                "source_id": str(account_id),
                "reason": "auth_error",
                "version": 0,
            },
        )
    async with engine.begin() as connection:
        second_id = await run_emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_id),
                "source_id": str(account_id),
                "reason": "scope_reduced",
                "version": 0,
            },
        )

    assert first_id != second_id
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
    assert len(rows) == 2
