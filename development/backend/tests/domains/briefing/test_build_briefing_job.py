from sqlalchemy import update

from app.core.database import engine
from app.domains.briefing import repository
from app.domains.briefing.jobs.build_briefing import handle_build_briefing_trigger
from app.domains.mail_intake.models import gmail_messages
from tests.domains.briefing.conftest import seed_message, seed_scope


async def test_summary_completed_rebuilds_single_message() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="summary_completed",
            workspace_id=workspace_id,
            message_ids=[m1],
            summary_text="이번 분기 정산 요약입니다.",
        )
        after_summary = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    assert after_summary["summary_text"] == "이번 분기 정산 요약입니다."
    assert after_summary["importance_band"] is None

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="importance_classified",
            workspace_id=workspace_id,
            message_ids=[m1],
            importance_band="fake_high",
        )
        after_importance = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    # importance_classified touched only its own column — summary_text from
    # the earlier trigger is preserved (briefing.md Job §동시).
    assert after_importance["summary_text"] == "이번 분기 정산 요약입니다."
    assert after_importance["importance_band"] == "fake_high"


async def test_snapshot_changed_no_importance_no_pending_item() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="gmail_snapshot_changed",
            workspace_id=workspace_id,
            message_ids=[m1],
        )
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    # No item-level pending state — importance_band is simply null, the
    # only "waiting" signal is account-level syncing (briefing.md §선행조건).
    assert item is not None
    assert item["importance_band"] is None


async def test_action_applied_reflects_done_state() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id, is_read=False)

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="gmail_snapshot_changed",
            workspace_id=workspace_id,
            message_ids=[m1],
        )
        before = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    # Simulate gmail_actions applying the mutation and mail_intake
    # reconciling the snapshot (out of scope for this isolated worktree —
    # briefing only reacts to the trigger and re-joins current state).
    async with engine.begin() as connection:
        await connection.execute(
            update(gmail_messages).where(gmail_messages.c.id == m1).values(is_read=True)
        )

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="gmail_action_applied",
            workspace_id=workspace_id,
            message_ids=[m1],
        )
        after = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )
        cards = await repository.list_briefing_cards_for_account(
            connection, connected_account_id=account_id
        )

    assert after["rebuilt_at"] > before["rebuilt_at"]
    card = next(c for c in cards if c["message_id"] == m1)
    assert card["is_read"] is True  # "done" derives from Gmail read state


async def test_partial_scope_only() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)
    m2 = await seed_message(account_id)

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="gmail_snapshot_changed",
            workspace_id=workspace_id,
            message_ids=[m1],
        )
        item1 = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )
        item2 = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m2
        )

    assert item1 is not None
    assert item2 is None  # payload didn't name m2 -> never rebuilt


async def test_job_idempotent() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="summary_completed",
            workspace_id=workspace_id,
            message_ids=[m1],
            summary_text="요약",
        )
        first = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    async with engine.begin() as connection:
        await handle_build_briefing_trigger(
            connection,
            trigger_type="summary_completed",
            workspace_id=workspace_id,
            message_ids=[m1],
            summary_text="요약",
        )
        second = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )
        all_items = await repository.list_briefing_items_for_account(
            connection, connected_account_id=account_id
        )

    assert first["id"] == second["id"]
    assert second["summary_text"] == "요약"
    assert len(all_items) == 1


async def test_build_briefing_job_handler_reads_official_payload_shape() -> None:
    """JOB_HANDLERS["build_briefing"] contract entry point —
    _integration-contract.md §2 payload `{workspace_id, source_id?,
    message_ids?}` (no summary_text/importance_band — those are
    handle_build_briefing_trigger-only test hooks, see its docstring)."""
    from app.domains.briefing.jobs.build_briefing import build_briefing_job

    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    await build_briefing_job(
        {"workspace_id": str(workspace_id), "message_ids": [str(m1)]}
    )

    async with engine.begin() as connection:
        item = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )
    assert item is not None
