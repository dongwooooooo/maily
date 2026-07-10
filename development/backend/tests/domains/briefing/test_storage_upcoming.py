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
    """Bucket boundary는 calendar-day UTC다(queries.get_storage_upcoming의
    today_start/tomorrow_start/day_after_tomorrow/week_end). 단순한 "now + fixed offset"
    test에서는 두 제약이 충돌한다. remind_at은 *real* wall-clock time 기준으로 반드시
    미래여야 하지만(reminders.schedule_reminder §선행조건), suite가 UTC 기준 토요일이나
    일요일에 실행되면 this_week window [day_after_tomorrow, week_end)가 비거나
    degenerate해진다(week_end는 항상 *next* Monday라서 day_after_tomorrow보다
    앞서거나 같을 수 있음).

    해결 방식은 "remind_at이 schedule되는 시점"과 "bucketing을 평가할 `now`"를
    분리하는 것이다. 실제 미래 reminder를 schedule하고(어떤 offset이든 reminders.py의
    future-check를 만족), 항상 real wall-clock을 쓰는 HTTP layer를 우회해
    get_storage_upcoming을 직접 호출하면서 `now`를 synthetic Tuesday noon으로 고정한다.
    그러면 suite가 실제 어떤 요일에 실행되든 today/tomorrow/this_week가 모두 비지 않는다.
    """
    workspace_id, user_id, account_id = await seed_scope()
    real_now = datetime.now(timezone.utc)

    # Tuesday noon이며 real_now 이후다. 아래 모든 remind_at(all >= query_now)이
    # real_now보다 크다는 것을 보장한다.
    days_until_tuesday = (1 - real_now.weekday()) % 7  # Monday=0 ... Tuesday=1 기준
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
