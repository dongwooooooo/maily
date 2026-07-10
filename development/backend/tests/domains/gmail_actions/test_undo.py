import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.core.errors import ConflictError, ValidationError
from app.core.outbox import outbox_events
from app.domains.gmail_actions import repository
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.jobs.execute_action import run_execute_action
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from app.domains.gmail_actions.undo import request_undo
from tests.domains.gmail_actions.conftest import seed_message, seed_scope


@pytest.fixture(autouse=True)
def _fresh_fake_mutator():
    mutator = FakeGmailMutationPort()
    execute_action.set_mutator(mutator)
    yield mutator
    execute_action.set_mutator(FakeGmailMutationPort())


async def _create_and_apply(
    *, action_type: str = "mark_read", initial_labels: set[str] | None = None
):
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    execute_action.get_mutator().seed_labels(message_id, initial_labels or {"UNREAD", "INBOX"})
    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=account_id,
        message_id=message_id,
        action_type=action_type,
        idempotency_key=str(uuid.uuid4()),
        requested_by=user_id,
    )
    async with engine.begin() as connection:
        command, _ = await request_gmail_action(connection, data)
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.connect() as connection:
        activity = await repository.get_activity_log_by_command(connection, command_id=command.id)
    return workspace_id, user_id, message_id, command, activity


async def test_undo_creates_reverse_command() -> None:
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read"
    )

    async with engine.begin() as connection:
        undo_result = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )

    assert undo_result.reverse_command_id is not None
    assert undo_result.original_command_id == command.id
    assert undo_result.undone_at is None

    async with engine.connect() as connection:
        original = await repository.get_command(connection, command_id=command.id)
        reverse = await repository.get_command(
            connection, command_id=undo_result.reverse_command_id
        )

    assert original["status"] == "compensating"
    assert original["version"] == 2  # 상태 전이: 0 -> applied(1) -> compensating(2)
    assert reverse["status"] == "pending"
    assert reverse["payload"] == {"add_label_ids": ["UNREAD"], "remove_label_ids": []}


async def test_undo_reverses_via_ledger_not_direct_gmail(
    _fresh_fake_mutator: FakeGmailMutationPort,
) -> None:
    """Undo는 undo.py에서 port를 직접 호출하지 않고 새 pending command만 insert한다.
    reverse command를 정상 execute_action path로 적용할 때 실제 Gmail state가 복구되고,
    그때에만 original command가 `undone`으로 바뀐다."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="archive"
    )
    assert _fresh_fake_mutator.current_labels(message_id) == {"UNREAD"}  # INBOX 제거됨

    async with engine.begin() as connection:
        undo_result = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )

    # Undo request만으로는 아직 Gmail state를 건드리면 안 된다.
    assert _fresh_fake_mutator.current_labels(message_id) == {"UNREAD"}

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=undo_result.reverse_command_id)

    assert _fresh_fake_mutator.current_labels(message_id) == {"UNREAD", "INBOX"}

    async with engine.connect() as connection:
        original = await repository.get_command(connection, command_id=command.id)
        undo_row = await repository.get_undo_action_by_activity(
            connection, activity_id=activity["id"]
        )

    assert original["status"] == "undone"
    assert original["version"] == 3  # 상태 전이: applied(1) -> compensating(2) -> undone(3)
    assert undo_row["undone_at"] is not None


async def test_undo_finalize_emits_gmail_action_undone_with_workspace_and_message_id(
    _fresh_fake_mutator: FakeGmailMutationPort,
) -> None:
    """IC4: gmail_action_undone은 workspace_id/message_id를 담는다
    (gmail_action_applied enrichment와 함께 추가). 그래서 build_briefing이 자체
    cross-domain lookup 없이 rebuild할 수 있다."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read"
    )

    async with engine.begin() as connection:
        undo_result = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=undo_result.reverse_command_id)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "gmail_action_undone")
            )
        ).mappings().all()
    row = next(r for r in rows if r["payload"]["command_id"] == str(command.id))

    assert row["payload"]["workspace_id"] == str(workspace_id)
    assert row["payload"]["message_id"] == str(message_id)


async def test_undo_finalize_skips_event_when_account_scope_missing(
    _fresh_fake_mutator: FakeGmailMutationPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[선행조건] 계정이 사라진 뒤(미래 purge 이후) undo가 완료돼도
    workspace_id: null 짜리 gmail_action_undone을 발행하지 않는다 —
    ledger 전이(undone)는 그대로 유지, 이벤트만 생략(코드리뷰 반영)."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read"
    )
    async with engine.begin() as connection:
        undo_result = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )

    # run_execute_action은 자체적으로 get_connected_account_scope를 두 번 호출한다
    # (pending-branch precondition check, 그다음 activity/undo backfill). reverse command가
    # 실제 적용되려면 둘 다 정상 성공해야 한다. _finalize_undo_if_reverse의 더 늦은 독립
    # lookup(세 번째 call)만 account가 사라진 상황을 simulate한다.
    real_get_scope = repository.get_connected_account_scope
    call_count = 0

    async def _scope_missing_from_third_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return await real_get_scope(*args, **kwargs)
        return None

    monkeypatch.setattr(repository, "get_connected_account_scope", _scope_missing_from_third_call)

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=undo_result.reverse_command_id)

    async with engine.connect() as connection:
        original = await repository.get_command(connection, command_id=command.id)
        rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "gmail_action_undone")
            )
        ).mappings().all()

    assert original["status"] == "undone"  # ledger transition은 영향 없음
    assert not any(r["payload"]["command_id"] == str(command.id) for r in rows)


async def test_undo_idempotent_via_undone_at() -> None:
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read"
    )
    async with engine.begin() as connection:
        first = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=first.reverse_command_id)

    async with engine.begin() as connection:
        second = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )

    assert second.undone_at is not None
    assert second.reverse_command_id == first.reverse_command_id


async def test_undo_rejected_while_reverse_in_flight() -> None:
    """[동시] 첫 reverse command가 applied되기 전의 두 번째 undo call은
    두 번째 reverse command를 만들면 안 된다."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read"
    )
    async with engine.begin() as connection:
        await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )

    with pytest.raises(ConflictError):
        async with engine.begin() as connection:
            await request_undo(
                connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
            )


async def test_undo_unavailable_rejected() -> None:
    """changed=False(이미 target state) -> undo할 것 없음 -> 422."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read", initial_labels={"INBOX"}  # UNREAD가 이미 없음
    )

    async with engine.connect() as connection:
        applied = await repository.get_command(connection, command_id=command.id)
    assert applied["changed"] is False

    with pytest.raises(ValidationError):
        async with engine.begin() as connection:
            await request_undo(
                connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
            )
