import uuid

from app.core.database import engine
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.rules import (
    approve_rule_suggestion,
    create_rule_suggestion_from_signal,
    list_rules,
)
from tests.domains.assistant_decisions.conftest import (
    seed_correction_signal,
    seed_message,
    seed_scope,
    seed_service_label,
)


async def _seed_signal(*, sender: str | None = "manager@example.com"):
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, sender=sender)
    label_id = await seed_service_label(workspace_id, name="업무")
    signal_id = await seed_correction_signal(
        message_id=message_id, service_label_id=label_id, actor_id=user_id
    )
    return workspace_id, user_id, account_id, message_id, label_id, signal_id


async def test_correction_creates_pending_suggestion() -> None:
    workspace_id, _, _, message_id, label_id, signal_id = await _seed_signal()

    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )

    assert suggestion is not None
    assert suggestion["status"] == "pending"
    assert suggestion["workspace_id"] == workspace_id
    assert suggestion["suggested_condition"] == {"sender": "manager@example.com"}


async def test_no_sender_pattern_skips_suggestion() -> None:
    """[선행조건] 매칭 조건이 비었거나 패턴 추출 불가 -> suggestion 미생성."""
    _, _, _, _, _, signal_id = await _seed_signal(sender=None)

    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )

    assert suggestion is None


async def test_reprocessing_same_signal_is_idempotent() -> None:
    """[멱등] 같은 correction_signal_id 재실행 -> 이미 pending suggestion
    있으면 중복 insert 안 함(신호당 제안 하나)."""
    _, _, _, _, _, signal_id = await _seed_signal()

    async with engine.begin() as connection:
        first = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )
    async with engine.begin() as connection:
        second = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )

    assert first["id"] == second["id"]


async def test_only_approved_becomes_active_rule() -> None:
    workspace_id, _, _, _, label_id, signal_id = await _seed_signal()
    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )

    async with engine.connect() as connection:
        rules_before = await repository.list_active_classification_rules(
            connection, workspace_id=workspace_id
        )
    assert rules_before == []

    async with engine.begin() as connection:
        approved = await approve_rule_suggestion(
            connection, suggestion_id=suggestion["id"], workspace_id=workspace_id
        )

    assert approved["status"] == "approved"
    async with engine.connect() as connection:
        rules_after = await repository.list_active_classification_rules(
            connection, workspace_id=workspace_id
        )
    assert len(rules_after) == 1
    assert rules_after[0]["service_label_id"] == label_id
    assert rules_after[0]["match_condition"] == {"sender": "manager@example.com"}


async def test_reapprove_is_noop() -> None:
    workspace_id, _, _, _, _, signal_id = await _seed_signal()
    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )
    async with engine.begin() as connection:
        await approve_rule_suggestion(
            connection, suggestion_id=suggestion["id"], workspace_id=workspace_id
        )
    async with engine.begin() as connection:
        second = await approve_rule_suggestion(
            connection, suggestion_id=suggestion["id"], workspace_id=workspace_id
        )

    async with engine.connect() as connection:
        rules = await repository.list_active_classification_rules(
            connection, workspace_id=workspace_id
        )
    assert second["status"] == "approved"
    assert len(rules) == 1  # 두 번째 approve call로 중복 생성되지 않음


async def test_approve_rejected_suggestion_conflicts() -> None:
    workspace_id, _, _, _, _, signal_id = await _seed_signal()
    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )
    async with engine.begin() as connection:
        await repository.mark_rule_suggestion_decided(
            connection,
            suggestion_id=suggestion["id"],
            status="rejected",
            decided_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )

    async with engine.begin() as connection:
        try:
            await approve_rule_suggestion(
                connection, suggestion_id=suggestion["id"], workspace_id=workspace_id
            )
            assert False, "expected ConflictError"
        except ConflictError:
            pass


async def test_approve_scoped_to_workspace() -> None:
    _, _, _, _, _, signal_id = await _seed_signal()
    async with engine.begin() as connection:
        suggestion = await create_rule_suggestion_from_signal(
            connection, correction_signal_id=signal_id
        )

    other_workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        try:
            await approve_rule_suggestion(
                connection, suggestion_id=suggestion["id"], workspace_id=other_workspace_id
            )
            assert False, "expected ForbiddenError"
        except ForbiddenError:
            pass


async def test_missing_correction_signal_rejects_job() -> None:
    async with engine.begin() as connection:
        try:
            await create_rule_suggestion_from_signal(
                connection, correction_signal_id=uuid.uuid4()
            )
            assert False, "expected NotFoundError"
        except NotFoundError:
            pass


async def test_list_rules_scoped() -> None:
    workspace_id, _, _, _, _, signal_id = await _seed_signal()
    async with engine.begin() as connection:
        await create_rule_suggestion_from_signal(connection, correction_signal_id=signal_id)

    other_workspace_id = uuid.uuid4()
    async with engine.connect() as connection:
        own_view = await list_rules(connection, workspace_id=workspace_id)
        other_view = await list_rules(connection, workspace_id=other_workspace_id)

    assert len(own_view["suggestions"]) == 1
    assert own_view["rules"] == []
    assert other_view["suggestions"] == []
    assert other_view["rules"] == []
