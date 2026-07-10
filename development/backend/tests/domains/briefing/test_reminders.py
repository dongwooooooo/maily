import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import engine
from app.core.errors import ValidationError
from app.domains.briefing import repository
from app.domains.briefing.reminders import schedule_reminder
from app.domains.briefing.service import rebuild_briefing
from tests.domains.briefing.conftest import seed_message, seed_scope


async def _seed_item() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[message_id])
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )
    return workspace_id, user_id, account_id, message_id, item["id"]


async def test_schedule_creates_reminder_and_state() -> None:
    workspace_id, user_id, _account_id, message_id, item_id = await _seed_item()
    remind_at = datetime.now(timezone.utc) + timedelta(hours=2)

    async with engine.begin() as connection:
        result = await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=remind_at,
            actor_id=user_id,
            workspace_id=workspace_id,
        )
        state = await repository.get_item_state_by_message(connection, message_id=message_id)
        pending = await repository.get_pending_reminder_by_state(
            connection, briefing_item_state_id=state["id"]
        )

    assert result.status == "pending"
    assert state["remind_later_at"] == remind_at
    assert pending is not None
    assert pending["remind_at"] == remind_at


async def test_reschedule_updates_pending() -> None:
    workspace_id, user_id, _account_id, message_id, item_id = await _seed_item()
    first_remind_at = datetime.now(timezone.utc) + timedelta(hours=2)
    second_remind_at = datetime.now(timezone.utc) + timedelta(hours=5)

    async with engine.begin() as connection:
        first = await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=first_remind_at,
            actor_id=user_id,
            workspace_id=workspace_id,
        )

    async with engine.begin() as connection:
        second = await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=second_remind_at,
            actor_id=user_id,
            workspace_id=workspace_id,
        )
        state = await repository.get_item_state_by_message(connection, message_id=message_id)
        all_pending = [
            r
            for r in (
                await repository.list_pending_reminders_for_workspace(
                    connection, workspace_id=workspace_id
                )
            )
            if r["message_id"] == message_id
        ]

    assert first.id == second.id  # 같은 reminder row update, 새 row 아님
    assert second.remind_at == second_remind_at
    assert state["remind_later_at"] == second_remind_at
    assert len(all_pending) == 1  # pending row 중복 없음


async def test_past_remind_at_rejected() -> None:
    workspace_id, user_id, _account_id, _message_id, item_id = await _seed_item()
    past = datetime.now(timezone.utc) - timedelta(hours=1)

    async with engine.begin() as connection:
        with pytest.raises(ValidationError):
            await schedule_reminder(
                connection,
                briefing_item_id=item_id,
                remind_at=past,
                actor_id=user_id,
                workspace_id=workspace_id,
            )


async def test_reminder_survives_rebuild() -> None:
    workspace_id, user_id, account_id, message_id, item_id = await _seed_item()
    remind_at = datetime.now(timezone.utc) + timedelta(hours=2)

    async with engine.begin() as connection:
        await schedule_reminder(
            connection,
            briefing_item_id=item_id,
            remind_at=remind_at,
            actor_id=user_id,
            workspace_id=workspace_id,
        )

    async with engine.begin() as connection:
        await repository.delete_briefing_items_for_workspace(connection, workspace_id=workspace_id)
        await rebuild_briefing(connection, workspace_id=workspace_id)
        state = await repository.get_item_state_by_message(connection, message_id=message_id)
        pending = [
            r
            for r in (
                await repository.list_pending_reminders_for_workspace(
                    connection, workspace_id=workspace_id
                )
            )
            if r["message_id"] == message_id
        ]

    assert state["remind_later_at"] == remind_at
    assert len(pending) == 1
