import uuid

from app.core.database import engine
from app.domains.briefing import repository
from app.domains.briefing.schemas import FAKE_SECTION
from app.domains.briefing.service import rebuild_briefing
from tests.domains.briefing.conftest import seed_message, seed_scope


async def test_partial_rebuild_single_message() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id, subject="m1")
    m2 = await seed_message(account_id, subject="m2")

    async with engine.begin() as connection:
        rebuilt = await rebuild_briefing(
            connection, workspace_id=workspace_id, message_ids=[m1]
        )
        item1 = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )
        item2 = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m2
        )

    assert rebuilt == [m1]
    assert item1 is not None
    assert item1["section"] == FAKE_SECTION
    assert item2 is None  # 변경 없음 — m2는 scope에 없었음


async def test_rebuild_idempotent() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[m1])
        first = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[m1])
        second = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )
        all_items = await repository.list_briefing_items_for_account(
            connection, connected_account_id=account_id
        )

    assert first["id"] == second["id"]  # upsert이며 두 번째 row가 아님
    assert len(all_items) == 1
    assert second["section"] == first["section"]
    assert second["importance_band"] == first["importance_band"]


async def test_rebuild_preserves_item_state() -> None:
    """Durable seen state(message_id-keyed)는 rebuild로 변경되지 않는다.
    briefing.md 강제 invariant이며 test_seen_state.py::test_seen_survives_rebuild에서
    다시 end-to-end로 검증한다."""
    from datetime import datetime, timezone

    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[m1])
        await repository.upsert_item_state(
            connection,
            state_id=uuid.uuid4(),
            workspace_id=workspace_id,
            message_id=m1,
            seen=True,
            seen_at=datetime.now(timezone.utc),
            remind_later_at=None,
            version=1,
            updated_at=datetime.now(timezone.utc),
        )

    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id, message_ids=[m1])
        state = await repository.get_item_state_by_message(connection, message_id=m1)

    assert state is not None
    assert state["seen"] is True


async def test_full_rebuild_workspace_scoped() -> None:
    workspace_a, _user_a, account_a = await seed_scope()
    workspace_b, _user_b, account_b = await seed_scope()
    m_a = await seed_message(account_a)
    m_b = await seed_message(account_b)

    async with engine.begin() as connection:
        rebuilt = await rebuild_briefing(connection, workspace_id=workspace_a)
        item_a = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_a, message_id=m_a
        )
        item_b = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_b, message_id=m_b
        )

    assert m_a in rebuilt
    assert m_b not in rebuilt
    assert item_a is not None
    assert item_b is None  # 다른 workspace의 message는 projection되지 않음
