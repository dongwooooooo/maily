import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.gmail_actions import repository
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


async def _create_pending_command(
    *, action_type: str = "mark_read", message_id: uuid.UUID | None = None
):
    workspace_id, user_id, account_id = await seed_scope()
    message_id = message_id or await seed_message(account_id)
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
    return workspace_id, user_id, account_id, message_id, command


async def test_execute_applies_and_emits(_fresh_fake_mutator: FakeGmailMutationPort) -> None:
    _fresh_fake_mutator.seed_labels(uuid.uuid4(), set())  # unrelated seed, no-op
    _, _, _, message_id, command = await _create_pending_command(action_type="mark_read")
    _fresh_fake_mutator.seed_labels(message_id, {"UNREAD", "INBOX"})

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.connect() as connection:
        updated = await repository.get_command(connection, command_id=command.id)

    assert updated["status"] == "applied"
    assert updated["version"] == 1
    assert updated["changed"] is True
    assert updated["applied_at"] is not None

    key = f"command:{command.id}:applied:1"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()
    assert row is not None
    assert row["event_type"] == "gmail_action_applied"


async def test_changed_false_on_noop(_fresh_fake_mutator: FakeGmailMutationPort) -> None:
    """[changed flag] mark_read on a message that's already read -> changed=False."""
    _, _, _, message_id, command = await _create_pending_command(action_type="mark_read")
    _fresh_fake_mutator.seed_labels(message_id, {"INBOX"})  # UNREAD already absent

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.connect() as connection:
        updated = await repository.get_command(connection, command_id=command.id)

    assert updated["status"] == "applied"
    assert updated["changed"] is False


async def test_execute_idempotent(_fresh_fake_mutator: FakeGmailMutationPort) -> None:
    """[멱등] re-running execute_action on an already-applied command is a
    no-op: no version bump, no duplicate activity_log."""
    _, _, _, message_id, command = await _create_pending_command(action_type="archive")
    _fresh_fake_mutator.seed_labels(message_id, {"INBOX", "UNREAD"})

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.connect() as connection:
        updated = await repository.get_command(connection, command_id=command.id)
        activity = await repository.get_activity_log_by_command(connection, command_id=command.id)

    assert updated["status"] == "applied"
    assert updated["version"] == 1  # still 1, not bumped again
    assert activity is not None


async def test_failure_sets_failed_and_emits(_fresh_fake_mutator: FakeGmailMutationPort) -> None:
    _, _, _, message_id, command = await _create_pending_command(action_type="mark_read")
    _fresh_fake_mutator.fail_next(command.id)

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.connect() as connection:
        updated = await repository.get_command(connection, command_id=command.id)
        activity = await repository.get_activity_log_by_command(connection, command_id=command.id)

    assert updated["status"] == "failed"
    assert updated["version"] == 1
    assert updated["error_reason"] is not None
    assert updated["applied_at"] is None
    assert activity is None  # no activity for a failed command

    key = f"command:{command.id}:failed:1"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()
    assert row is not None
    assert row["event_type"] == "gmail_action_failed"


async def test_pending_becomes_blocked_when_account_disconnecting(
    _fresh_fake_mutator: FakeGmailMutationPort,
) -> None:
    """[선행조건] account disconnecting -> execution stops, command stays pending."""
    from sqlalchemy import update

    from app.domains.mail_sources.models import connected_gmail_accounts

    _, _, account_id, message_id, command = await _create_pending_command(action_type="mark_read")
    async with engine.begin() as connection:
        await connection.execute(
            update(connected_gmail_accounts)
            .where(connected_gmail_accounts.c.id == account_id)
            .values(status="disconnecting")
        )

    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.connect() as connection:
        updated = await repository.get_command(connection, command_id=command.id)
    assert updated["status"] == "pending"
