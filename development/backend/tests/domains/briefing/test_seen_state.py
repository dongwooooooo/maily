import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.core.errors import ForbiddenError, NotFoundError
from app.core.outbox import outbox_events
from app.domains.briefing import repository
from app.domains.briefing.item_state import set_item_seen
from app.domains.briefing.service import rebuild_briefing
from tests.domains.briefing.conftest import seed_message, seed_scope


async def _seed_item(**scope_overrides) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    workspace_id, user_id, account_id = await seed_scope(**scope_overrides)
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[message_id])
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )
    return workspace_id, user_id, message_id, item["id"]


async def test_seen_upserts_and_emits() -> None:
    workspace_id, user_id, message_id, item_id = await _seed_item()

    async with engine.begin() as connection:
        result, is_new = await set_item_seen(
            connection, briefing_item_id=item_id, actor_id=user_id, workspace_id=workspace_id
        )
        all_events = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "briefing_item_state_changed")
            )
        ).mappings().all()
        events_for_message = [
            e for e in all_events if e["payload"]["message_id"] == str(message_id)
        ]

    assert is_new is True
    assert result.seen is True
    assert result.seen_at is not None
    assert result.message_id == message_id
    assert len(events_for_message) == 1


async def test_seen_survives_rebuild() -> None:
    workspace_id, user_id, message_id, item_id = await _seed_item()

    async with engine.begin() as connection:
        await set_item_seen(
            connection, briefing_item_id=item_id, actor_id=user_id, workspace_id=workspace_id
        )

    account_id = None
    async with engine.begin() as connection:
        item_before = await repository.get_briefing_item(connection, item_id=item_id)
        account_id = item_before["connected_account_id"]
        await repository.delete_briefing_items_for_workspace(connection, workspace_id=workspace_id)
        await rebuild_briefing(connection, workspace_id=workspace_id)
        new_item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )
        cards = await repository.list_briefing_cards_for_account(
            connection, connected_account_id=account_id
        )

    assert new_item is not None
    card = next(c for c in cards if c["message_id"] == message_id)
    assert card["seen"] is True


async def test_noop_seen_no_event() -> None:
    workspace_id, user_id, message_id, item_id = await _seed_item()

    async with engine.begin() as connection:
        _, first_is_new = await set_item_seen(
            connection, briefing_item_id=item_id, actor_id=user_id, workspace_id=workspace_id
        )

    async with engine.begin() as connection:
        result, second_is_new = await set_item_seen(
            connection, briefing_item_id=item_id, actor_id=user_id, workspace_id=workspace_id
        )
        all_events = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "briefing_item_state_changed")
            )
        ).mappings().all()
        events_for_message = [
            e for e in all_events if e["payload"]["message_id"] == str(message_id)
        ]

    assert first_is_new is True
    assert second_is_new is False
    assert len(events_for_message) == 1  # no second event on the no-op repeat
    assert result.version == 1


async def test_seen_scoped_to_workspace() -> None:
    _workspace_id, _user_id, message_id, item_id = await _seed_item()
    other_workspace_id, other_user_id, _other_account = await seed_scope()

    async with engine.begin() as connection:
        with pytest.raises(ForbiddenError):
            await set_item_seen(
                connection,
                briefing_item_id=item_id,
                actor_id=other_user_id,
                workspace_id=other_workspace_id,
            )


async def test_seen_unknown_item_not_found() -> None:
    workspace_id, user_id, _account_id = await seed_scope()

    async with engine.begin() as connection:
        with pytest.raises(NotFoundError):
            await set_item_seen(
                connection,
                briefing_item_id=uuid.uuid4(),
                actor_id=user_id,
                workspace_id=workspace_id,
            )
