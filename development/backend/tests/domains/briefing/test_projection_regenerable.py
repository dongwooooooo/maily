from app.core.database import engine
from app.domains.briefing import repository
from app.domains.briefing.service import rebuild_briefing
from tests.domains.briefing.conftest import seed_message, seed_scope


async def test_drop_and_rebuild_matches_source() -> None:
    """briefing_items는 재생성 가능한 projection이다. workspace의 모든 row를 drop하고
    gmail_messages에서 rebuild하면 같은 (connected_account_id, message_id) pair set이
    재현되어야 한다(briefing.md 강제 invariant:
    "언제든 drop-and-rebuild 가능해야 한다")."""
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id, subject="m1")
    m2 = await seed_message(account_id, subject="m2")

    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id)
        before = {
            item["message_id"]
            for item in await repository.list_briefing_items_for_account(
                connection, connected_account_id=account_id
            )
        }

    async with engine.begin() as connection:
        await repository.delete_briefing_items_for_workspace(connection, workspace_id=workspace_id)
        dropped = await repository.list_briefing_items_for_account(
            connection, connected_account_id=account_id
        )

    assert dropped == []

    async with engine.begin() as connection:
        await rebuild_briefing(connection, workspace_id=workspace_id)
        after = {
            item["message_id"]
            for item in await repository.list_briefing_items_for_account(
                connection, connected_account_id=account_id
            )
        }

    assert before == after == {m1, m2}
