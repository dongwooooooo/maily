import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import engine
from app.domains.briefing import repository
from app.domains.briefing.jobs.reactivate_reminders import run_reactivate_reminders
from app.domains.briefing.queries import get_storage_upcoming
from app.domains.briefing.reminders import schedule_reminder
from app.domains.briefing.service import rebuild_briefing
from app.domains.identity.service import issue_session
from app.main import app
from tests.domains.briefing.conftest import seed_message, seed_scope


async def _headers_for(user_id: uuid.UUID, workspace_id: uuid.UUID) -> dict:
    async with engine.begin() as connection:
        token = await issue_session(connection, user_id=user_id, workspace_id=workspace_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_item(workspace_id, account_id):
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[message_id])
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )
    return message_id, item["id"]


async def test_grouped_today_tomorrow_week() -> None:
    """Bucket boundaries are calendar-day UTC (queries.get_storage_upcoming
    today_start/tomorrow_start/day_after_tomorrow/week_end). Two
    constraints fight each other for a naive "now + fixed offset" test:
    remind_at must be strictly in the future in *real* wall-clock time
    (reminders.schedule_reminder §선행조건), but the this_week window
    [day_after_tomorrow, week_end) is empty/degenerate whenever the suite
    happens to run on a Saturday or Sunday UTC (week_end is always the
    *next* Monday, so it can fall before or at day_after_tomorrow).

    Resolved by decoupling "when remind_at is scheduled for" from "what
    `now` the bucketing is evaluated against": schedule real, future
    reminders (any offset satisfies reminders.py's future-check), then
    call get_storage_upcoming directly (bypassing the HTTP layer, which
    always uses real wall-clock) with an explicit `now` pinned to a
    synthetic Tuesday noon — always mid-week, so today/tomorrow/this_week
    are all non-empty regardless of which real weekday the suite runs on.
    """
    workspace_id, user_id, account_id = await seed_scope()
    real_now = datetime.now(timezone.utc)

    # Tuesday noon, at or after real_now — guarantees every remind_at
    # below (all >= query_now) is also > real_now.
    days_until_tuesday = (1 - real_now.weekday()) % 7  # Monday=0 ... Tuesday=1
    query_now = (real_now + timedelta(days=days_until_tuesday)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    if query_now <= real_now:
        query_now += timedelta(days=7)

    today_start = query_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    day_after_tomorrow = tomorrow_start + timedelta(days=1)

    _m_today, item_today = await _seed_item(workspace_id, account_id)
    _m_tomorrow, item_tomorrow = await _seed_item(workspace_id, account_id)
    _m_week, item_week = await _seed_item(workspace_id, account_id)

    async with engine.begin() as connection:
        await schedule_reminder(
            connection,
            briefing_item_id=item_today,
            remind_at=query_now,
            actor_id=user_id,
            workspace_id=workspace_id,
        )
    async with engine.begin() as connection:
        await schedule_reminder(
            connection,
            briefing_item_id=item_tomorrow,
            remind_at=tomorrow_start + timedelta(hours=1),
            actor_id=user_id,
            workspace_id=workspace_id,
        )
    async with engine.begin() as connection:
        await schedule_reminder(
            connection,
            briefing_item_id=item_week,
            remind_at=day_after_tomorrow + timedelta(days=1),
            actor_id=user_id,
            workspace_id=workspace_id,
        )

    async with engine.connect() as connection:
        upcoming = await get_storage_upcoming(
            connection, workspace_id=workspace_id, now=query_now
        )

    assert len(upcoming.today) == 1
    assert len(upcoming.tomorrow) == 1
    assert len(upcoming.this_week) == 1


async def test_pending_only() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    now = datetime.now(timezone.utc)
    _message_id, item_id = await _seed_item(workspace_id, account_id)

    async with engine.begin() as connection:
        result = await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=now + timedelta(hours=1),
            actor_id=user_id,
            workspace_id=workspace_id,
        )
    async with engine.begin() as connection:
        from sqlalchemy import update

        from app.domains.briefing.models import reminders

        await connection.execute(
            update(reminders)
            .where(reminders.c.id == result.id)
            .values(status="cancelled")
        )
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/storage/upcoming", headers=headers)
    body = response.json()

    assert body["today"] == []
    assert body["tomorrow"] == []
    assert body["this_week"] == []


async def test_past_reactivated_not_in_storage() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    now = datetime.now(timezone.utc)
    _message_id, item_id = await _seed_item(workspace_id, account_id)

    async with engine.begin() as connection:
        result = await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=now + timedelta(hours=1),
            actor_id=user_id,
            workspace_id=workspace_id,
        )
    async with engine.begin() as connection:
        from sqlalchemy import update

        from app.domains.briefing.models import reminders

        await connection.execute(
            update(reminders).where(reminders.c.id == result.id).values(
                remind_at=now - timedelta(minutes=5)
            )
        )
    async with engine.begin() as connection:
        await run_reactivate_reminders(connection)

    headers = await _headers_for(user_id, workspace_id)
    client = TestClient(app)
    response = client.get("/storage/upcoming", headers=headers)
    body = response.json()

    assert body["today"] == []
    assert body["tomorrow"] == []
    assert body["this_week"] == []


async def test_empty_state() -> None:
    workspace_id, user_id, _account_id = await seed_scope()
    headers = await _headers_for(user_id, workspace_id)

    client = TestClient(app)
    response = client.get("/storage/upcoming", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body == {"today": [], "tomorrow": [], "this_week": []}


async def test_scoped_to_workspace() -> None:
    workspace_a, user_a, account_a = await seed_scope()
    workspace_b, user_b, _account_b = await seed_scope()
    now = datetime.now(timezone.utc)
    _message_id, item_id = await _seed_item(workspace_a, account_a)

    async with engine.begin() as connection:
        await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=now + timedelta(hours=1),
            actor_id=user_a,
            workspace_id=workspace_a,
        )
    headers_b = await _headers_for(user_b, workspace_b)

    client = TestClient(app)
    response = client.get("/storage/upcoming", headers=headers_b)
    body = response.json()

    assert body == {"today": [], "tomorrow": [], "this_week": []}
