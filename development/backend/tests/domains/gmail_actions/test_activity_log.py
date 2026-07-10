import uuid
from datetime import datetime, timezone

import pytest

from app.core.database import engine
from app.domains.gmail_actions import repository
from app.domains.gmail_actions.activity import list_activity
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.jobs.execute_action import run_execute_action
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from tests.domains.gmail_actions.conftest import seed_message, seed_scope


@pytest.fixture(autouse=True)
def _fresh_fake_mutator():
    mutator = FakeGmailMutationPort()
    execute_action.set_mutator(mutator)
    yield mutator
    execute_action.set_mutator(FakeGmailMutationPort())


async def _create_and_apply(*, action_type: str = "mark_read", initial_labels=None):
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
    return workspace_id, user_id, command


async def test_activity_created_on_apply() -> None:
    workspace_id, user_id, command = await _create_and_apply()

    async with engine.connect() as connection:
        activity = await repository.get_activity_log_by_command(connection, command_id=command.id)

    assert activity is not None
    assert activity["workspace_id"] == workspace_id
    assert activity["actor_id"] == user_id
    assert activity["occurred_at"] is not None


async def test_activity_excludes_message_body() -> None:
    """강제 invariant: activity_logs.action_summary는 message body/summary
    텍스트를 포함하지 않는다 — payload에 없는 정보를 요약에 넣을 방법이 없다는
    것을 구조적으로 보여준다(요약은 action_type에서만 파생)."""
    workspace_id, user_id, command = await _create_and_apply(action_type="archive")

    async with engine.connect() as connection:
        activity = await repository.get_activity_log_by_command(connection, command_id=command.id)

    assert activity is not None
    forbidden_substrings = ["<html", "Subject:", "From:", "body", "요약:"]
    for token in forbidden_substrings:
        assert token not in activity["action_summary"]
    assert len(activity["action_summary"]) < 200


async def test_activity_reconstructable_from_ledger() -> None:
    """[부분실패] Gmail mutation은 성공했지만 activity_log insert는 일어나지 않았다
    (둘 사이의 crash를 simulate). ledger(command row, status=applied/changed)가
    여전히 source of truth이므로 ensure/backfill path를 재실행하면 mutation port를
    다시 호출하지 않고 activity_log를 결정적으로 복원해야 한다."""
    from app.domains.gmail_actions.activity import ensure_activity_and_undo

    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=account_id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=str(uuid.uuid4()),
        requested_by=user_id,
    )
    async with engine.begin() as connection:
        command, _ = await request_gmail_action(connection, data)

    # Gmail은 성공했고 command도 applied로 표시됐지만, activity_log insert가 commit되기
    # 전에 process가 죽은 상황을 흉내낸다.
    async with engine.begin() as connection:
        await repository.mark_command_applied(
            connection,
            command_id=command.id,
            version=1,
            changed=True,
            applied_at=datetime.now(timezone.utc),
        )

    async with engine.connect() as connection:
        assert await repository.get_activity_log_by_command(connection, command_id=command.id) is None

    # Recovery: 이제 applied 상태인 ledger row에 대해 backfill을 재실행한다.
    async with engine.begin() as connection:
        applied_command = await repository.get_command(connection, command_id=command.id)
        scope = await repository.get_connected_account_scope(
            connection, connected_account_id=account_id
        )
        activity_row, undo_row = await ensure_activity_and_undo(
            connection,
            command=applied_command,
            workspace_id=scope["workspace_id"],
            actor_id=applied_command["requested_by"],
        )

    assert activity_row is not None
    assert activity_row["command_id"] == command.id
    assert undo_row is not None
    assert undo_row["undo_available"] is True

    # 다시 실행해도 두 번째 activity_log row를 만들면 안 된다.
    async with engine.begin() as connection:
        applied_command = await repository.get_command(connection, command_id=command.id)
        scope = await repository.get_connected_account_scope(
            connection, connected_account_id=account_id
        )
        second_activity, _ = await ensure_activity_and_undo(
            connection,
            command=applied_command,
            workspace_id=scope["workspace_id"],
            actor_id=applied_command["requested_by"],
        )
    assert second_activity["id"] == activity_row["id"]


async def test_activity_list_scoped_no_body() -> None:
    workspace_id, user_id, command = await _create_and_apply()
    other_workspace_id, other_user_id, other_account_id = await seed_scope()

    async with engine.connect() as connection:
        entries = await list_activity(connection, workspace_id=workspace_id)
        other_entries = await list_activity(connection, workspace_id=other_workspace_id)

    assert any(entry.command_id == command.id for entry in entries)
    assert other_entries == []
    for entry in entries:
        assert entry.workspace_id == workspace_id


async def test_activity_list_empty_is_not_an_error() -> None:
    workspace_id, _ = (await seed_scope())[:2]

    async with engine.connect() as connection:
        entries = await list_activity(connection, workspace_id=workspace_id)

    assert entries == []
