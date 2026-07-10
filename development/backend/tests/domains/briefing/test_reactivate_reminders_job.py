import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.briefing import repository
from app.domains.briefing.jobs.reactivate_reminders import run_reactivate_reminders
from app.domains.briefing.reminders import schedule_reminder
from app.domains.briefing.service import rebuild_briefing
from tests.domains.briefing.conftest import seed_message, seed_scope


async def _seed_reminder(remind_at: datetime) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """(workspace_id, message_id, reminder_id)를 반환한다. reactivation test에서
    past-due reminder를 seed할 수 있도록 schedule_reminder의 future-only guard를
    우회해 remind_at을 직접 설정한다."""
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[message_id])
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )
    future = datetime.now(timezone.utc) + timedelta(days=1)
    async with engine.begin() as connection:
        result = await schedule_reminder(
            connection,
            briefing_item_id=item["id"],
            remind_at=future,
            actor_id=user_id,
            workspace_id=workspace_id,
        )
    async with engine.begin() as connection:
        from sqlalchemy import update

        from app.domains.briefing.models import reminders

        await connection.execute(
            update(reminders).where(reminders.c.id == result.id).values(remind_at=remind_at)
        )
    return workspace_id, message_id, result.id


async def test_due_reminder_reactivates_and_emits() -> None:
    workspace_id, message_id, reminder_id = await _seed_reminder(
        datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    async with engine.begin() as connection:
        reactivated = await run_reactivate_reminders(connection)
        events = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "reminder_reactivated")
            )
        ).mappings().all()
        reminder = await repository.get_pending_reminder_by_state(
            connection,
            briefing_item_state_id=(
                await repository.get_item_state_by_message(connection, message_id=message_id)
            )["id"],
        )

    assert reminder_id in reactivated
    matching = [e for e in events if e["payload"]["reminder_id"] == str(reminder_id)]
    assert len(matching) == 1
    assert reminder is None  # 더 이상 pending 아님


async def test_reactivate_idempotent() -> None:
    _workspace_id, _message_id, reminder_id = await _seed_reminder(
        datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    async with engine.begin() as connection:
        first = await run_reactivate_reminders(connection)

    async with engine.begin() as connection:
        second = await run_reactivate_reminders(connection)
        events = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "reminder_reactivated")
            )
        ).mappings().all()

    assert reminder_id in first
    assert reminder_id not in second  # 이미 reactivated되어 다시 선택되지 않음
    matching = [e for e in events if e["payload"]["reminder_id"] == str(reminder_id)]
    assert len(matching) == 1


async def test_pending_only_picked() -> None:
    future_workspace, future_message, future_reminder = await _seed_reminder(
        datetime.now(timezone.utc) + timedelta(days=2)
    )

    async with engine.begin() as connection:
        reactivated = await run_reactivate_reminders(connection)

    assert future_reminder not in reactivated  # remind_at이 아직 due 아님


async def test_concurrent_no_double_reactivate() -> None:
    """같은 due reminder를 두 scan이 동시에 잡는 상황이다. conditional
    `WHERE status='pending'` update 덕분에 한 caller만 non-None result를
    관측한다(briefing.md Job §동시)."""
    _workspace_id, _message_id, reminder_id = await _seed_reminder(
        datetime.now(timezone.utc) - timedelta(minutes=5)
    )

    async with engine.begin() as connection:
        first = await repository.reactivate_reminder_if_pending(
            connection, reminder_id=reminder_id, reactivated_at=datetime.now(timezone.utc)
        )
        second = await repository.reactivate_reminder_if_pending(
            connection, reminder_id=reminder_id, reactivated_at=datetime.now(timezone.utc)
        )

    assert first is not None
    assert second is None
