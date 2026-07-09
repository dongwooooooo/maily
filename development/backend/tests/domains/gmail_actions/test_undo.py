import uuid

import pytest

from app.core.database import engine
from app.core.errors import ConflictError, ValidationError
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
    assert original["version"] == 2  # 0 -> applied(1) -> compensating(2)
    assert reverse["status"] == "pending"
    assert reverse["payload"] == {"add_label_ids": ["UNREAD"], "remove_label_ids": []}


async def test_undo_reverses_via_ledger_not_direct_gmail(
    _fresh_fake_mutator: FakeGmailMutationPort,
) -> None:
    """Undo never calls the port directly from undo.py — it only inserts a
    new pending command. Applying that reverse command through the normal
    execute_action path is what actually restores Gmail state, and only then
    does the original command flip to `undone`."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="archive"
    )
    assert _fresh_fake_mutator.current_labels(message_id) == {"UNREAD"}  # INBOX removed

    async with engine.begin() as connection:
        undo_result = await request_undo(
            connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
        )

    # Undo request alone must not have touched Gmail state yet.
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
    assert original["version"] == 3  # applied(1) -> compensating(2) -> undone(3)
    assert undo_row["undone_at"] is not None


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
    """[동시] a second undo call before the first reverse command has
    applied must not create a second reverse command."""
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
    """changed=False (already in target state) -> nothing to undo -> 422."""
    workspace_id, user_id, message_id, command, activity = await _create_and_apply(
        action_type="mark_read", initial_labels={"INBOX"}  # UNREAD already absent
    )

    async with engine.connect() as connection:
        applied = await repository.get_command(connection, command_id=command.id)
    assert applied["changed"] is False

    with pytest.raises(ValidationError):
        async with engine.begin() as connection:
            await request_undo(
                connection, activity_id=activity["id"], workspace_id=workspace_id, actor_id=user_id
            )
