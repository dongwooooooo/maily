"""IC7 (docs/goals/backend-plans/_build-schedule.md) — 알림 라우팅.

Real chain: briefing.run_reactivate_reminders(real producer, past-due reminder는
tests/domains/briefing/test_reactivate_reminders_job.py처럼 직접 seed)가 이 IC에서 추가된
workspace_id/message_id enrichment를 담아 reminder_reactivated를 emit한다 -> dispatch가 이를
build_briefing(message-scoped rebuild)과 emit_notification 둘 다로 fan-out한다
({trigger, payload}로 wrap됨. outbox_dispatcher._wrap_for_emit_notification 기준 generic
pass-through만으로는 만들 수 없는 shape) -> 둘을 실행하면 단순히 error 없이 실행된 job이
아니라, resolved route_target을 가진 실제 notification_events row가 생긴다.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.core.database import engine
from app.core.discovery import register_discovered_jobs
from app.core.jobs import registry
from app.core.jobs.dispatcher import run_job
from app.core.jobs.models import job_runs
from app.core.jobs.outbox_dispatcher import dispatch_pending_events
from app.core.jobs.wiring import ACTIVE_EVENT_CONSUMERS
from app.domains.briefing import repository as briefing_repository
from app.domains.briefing.jobs.reactivate_reminders import reactivate_reminders_job
from app.domains.briefing.models import reminders
from app.domains.briefing.reminders import schedule_reminder
from app.domains.briefing.service import rebuild_briefing
from app.domains.notifications import repository as notifications_repository
from tests.domains.briefing.conftest import seed_message, seed_scope


@pytest.fixture(autouse=True)
def _registered_jobs():
    register_discovered_jobs()
    yield
    registry.clear()


async def _run_all(job_ids: list[uuid.UUID]) -> None:
    for job_id in job_ids:
        async with engine.begin() as connection:
            status = await run_job(connection, job_id=job_id, worker_id="ic7-test")
        assert status == "succeeded"


async def test_reminder_reactivated_rebuilds_briefing_and_emits_notification() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[message_id])
        item = await briefing_repository.get_briefing_item_by_account_message(
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
        await connection.execute(
            update(reminders)
            .where(reminders.c.id == result.id)
            .values(remind_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        )

    # Producer: 실제 reactivate_reminders job(due-scan).
    await reactivate_reminders_job({})

    # Dispatch 단계: reminder_reactivated -> build_briefing + emit_notification.
    async with engine.begin() as connection:
        enqueued = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        rows = (await connection.execute(select(job_runs).where(job_runs.c.id.in_(enqueued)))).mappings().all()
    relevant = [
        r
        for r in rows
        if str(message_id) in r["payload"].get("message_ids", [])
        or r["payload"].get("payload", {}).get("message_id") == str(message_id)
    ]
    assert sorted(r["job_type"] for r in relevant) == ["build_briefing", "emit_notification"]
    await _run_all([r["id"] for r in relevant])

    async with engine.connect() as connection:
        notif_rows = await notifications_repository.list_notification_events(
            connection, workspace_id=workspace_id
        )

    assert len(notif_rows) == 1
    assert notif_rows[0]["notification_type"] == "reminder_due"
    assert notif_rows[0]["route_target"]["item_id"] == str(message_id)
