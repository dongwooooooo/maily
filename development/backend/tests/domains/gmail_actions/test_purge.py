import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.jobs.execute_action import run_execute_action
from app.domains.gmail_actions.models import gmail_action_commands
from app.domains.gmail_actions.purge import purge_source
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from tests.domains.gmail_actions.conftest import seed_message, seed_scope


@pytest.fixture(autouse=True)
def _fresh_fake_mutator():
    mutator = FakeGmailMutationPort()
    execute_action.set_mutator(mutator)
    yield mutator
    execute_action.set_mutator(FakeGmailMutationPort())


async def test_purge_nulls_message_id_keeps_command_row() -> None:
    """module-boundaries.md §8: gmail_actions keeps minimal activity audit —
    purge releases the message_id FK but never deletes the command row."""
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
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_action_commands).where(gmail_action_commands.c.id == command.id))
        ).mappings().first()

    assert row is not None
    assert row["message_id"] is None
    assert row["action_type"] == "mark_read"  # audit trail preserved


async def test_purge_only_affects_target_account() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    other_account_id = await seed_scope()
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

    async with engine.begin() as connection:
        await purge_source(connection, source_id=other_account_id[2])

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_action_commands).where(gmail_action_commands.c.id == command.id))
        ).mappings().first()

    assert row["message_id"] == message_id  # untouched — different account
