from sqlalchemy import update

from app.core.database import engine
from app.domains.assistant_decisions import repository as assistant_repository
from app.domains.briefing import repository
from app.domains.briefing.jobs.build_briefing import handle_build_briefing_trigger
from app.domains.mail_intake.models import gmail_messages
from tests.domains.briefing.conftest import seed_message, seed_scope


async def test_summary_completed_rebuilds_single_message() -> None:
    """[IC3] summary_completed 트리거 -> rebuild가 message_summaries를
    실제로 재조회해 summary_text에 반영한다(더 이상 payload override 아님)."""
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await assistant_repository.upsert_message_summary(
            connection,
            message_id=m1,
            summary_text="이번 분기 정산 요약입니다.",
            is_metadata_only=False,
            model_name="fake-model",
        )
        await handle_build_briefing_trigger(
            connection,
            trigger_type="summary_completed",
            workspace_id=workspace_id,
            message_ids=[m1],
        )
        after_summary = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    assert after_summary["summary_text"] == "이번 분기 정산 요약입니다."
    assert after_summary["importance_band"] is None

    async with engine.begin() as connection:
        await assistant_repository.upsert_message_importance_classification(
            connection, message_id=m1, importance_band="fake_high", reason="fake reason"
        )
        await handle_build_briefing_trigger(
            connection,
            trigger_type="importance_classified",
            workspace_id=workspace_id,
            message_ids=[m1],
        )
        after_importance = await repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=m1
        )

    # importance_classified는 실제 table 둘을 다시 읽는다. 이전 trigger가 설정한
    # summary_text가 남아 있는 이유는 message_summaries 자체가 바뀌지 않았기 때문이지,
    # 별도 override bookkeeping 때문이 아니다(briefing.md Job §동시).
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

    # item-level pending state는 없다. importance_band는 단순히 null이고,
    # 유일한 "waiting" signal은 account-level syncing이다(briefing.md §선행조건).
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

    # gmail_actions가 mutation을 적용하고 mail_intake가 snapshot을 reconcile한 상황을
    # simulate한다(이 isolated worktree의 범위 밖이다. briefing은 trigger에 반응해
    # current state를 다시 join할 뿐이다).
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
    assert card["is_read"] is True  # "done"은 Gmail read state에서 파생된다


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
    assert item2 is None  # payload가 m2를 지목하지 않음 -> rebuild되지 않음


async def test_job_idempotent() -> None:
    workspace_id, _user_id, account_id = await seed_scope()
    m1 = await seed_message(account_id)

    async with engine.begin() as connection:
        await assistant_repository.upsert_message_summary(
            connection, message_id=m1, summary_text="요약", is_metadata_only=False, model_name="fake-model"
        )
        await handle_build_briefing_trigger(
            connection,
            trigger_type="summary_completed",
            workspace_id=workspace_id,
            message_ids=[m1],
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
    """JOB_HANDLERS["build_briefing"] contract 진입점 —
    _integration-contract.md §2 payload `{workspace_id, source_id?,
    message_ids?}`를 읽는다(summary_text/importance_band 없음. 둘은
    handle_build_briefing_trigger 전용 test hook이며 해당 docstring 참고)."""
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
