from datetime import datetime, timedelta, timezone

from app.core.database import engine
from app.domains.briefing import repository
from app.domains.briefing import purge_source
from app.domains.briefing.reminders import schedule_reminder
from app.domains.briefing.service import rebuild_briefing
from tests.domains.briefing.conftest import seed_message, seed_scope


async def test_purge_source_removes_items_states_and_reminders() -> None:
    """PURGE_HANDLER(source_id) — content-bearing briefing_items/
    briefing_item_states are purged on source disconnect; reminders
    cascade via briefing_item_state_id (briefing.md "워크트리 격리 노트")."""
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[message_id])
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )

    async with engine.begin() as connection:
        await schedule_reminder(
            connection,
            briefing_item_id=item["id"],
            remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
            actor_id=user_id,
            workspace_id=workspace_id,
        )

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)
        remaining_item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )
        remaining_state = await repository.get_item_state_by_message(
            connection, message_id=message_id
        )
        remaining_pending = await repository.list_pending_reminders_for_workspace(
            connection, workspace_id=workspace_id
        )

    assert remaining_item is None
    assert remaining_state is None
    assert remaining_pending == []
