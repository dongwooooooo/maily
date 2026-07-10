import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.outbox import outbox_events
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from tests.domains.gmail_actions.conftest import seed_message, seed_scope


async def _make_input(**overrides) -> RequestGmailActionInput:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    defaults = {
        "workspace_id": workspace_id,
        "connected_account_id": account_id,
        "message_id": message_id,
        "action_type": "mark_read",
        "gmail_label_id": None,
        "idempotency_key": str(uuid.uuid4()),
        "requested_by": user_id,
    }
    defaults.update(overrides)
    return RequestGmailActionInput(**defaults)


@pytest.mark.parametrize(
    ("action_type", "gmail_label_id", "expected_payload"),
    [
        ("mark_read", None, {"add_label_ids": [], "remove_label_ids": ["UNREAD"]}),
        ("archive", None, {"add_label_ids": [], "remove_label_ids": ["INBOX"]}),
        (
            "read_and_archive",
            None,
            {"add_label_ids": [], "remove_label_ids": ["UNREAD", "INBOX"]},
        ),
        ("label_apply", "Label_123", {"add_label_ids": ["Label_123"], "remove_label_ids": []}),
    ],
)
async def test_request_creates_pending_command(action_type, gmail_label_id, expected_payload) -> None:
    data = await _make_input(action_type=action_type, gmail_label_id=gmail_label_id)

    async with engine.begin() as connection:
        command, is_new = await request_gmail_action(connection, data)

    assert is_new is True
    assert command.status == "pending"
    assert command.version == 0
    assert command.changed is None
    assert command.payload == expected_payload
    assert command.applied_at is None
    assert command.failed_at is None


async def test_action_payload_shape_is_uniform_add_remove_arrays() -> None:
    """docs/goals/backend-plans/gmail_actions.md: payload는 action_type과 무관하게
    항상 {add_label_ids, remove_label_ids}이며 per-type shape가 아니다."""
    data = await _make_input(action_type="archive")

    async with engine.begin() as connection:
        command, _ = await request_gmail_action(connection, data)

    assert set(command.payload.keys()) == {"add_label_ids", "remove_label_ids"}


async def test_request_appends_gmail_action_requested_event() -> None:
    data = await _make_input()

    async with engine.begin() as connection:
        command, _ = await request_gmail_action(connection, data)

    key = f"command:{command.id}:requested"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()

    assert row is not None
    assert row["event_type"] == "gmail_action_requested"
    assert row["producer_domain"] == "gmail_actions"
    assert row["payload"]["command_id"] == str(command.id)


async def test_idempotency_key_dedupes_mutation() -> None:
    """[멱등] 버튼 두 번 = mutation 한 번: 같은 idempotency_key는 같은 command를
    반환하며, 두 번째 row와 두 번째 event를 만들지 않는다."""
    key = str(uuid.uuid4())
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=account_id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=key,
        requested_by=user_id,
    )

    async with engine.begin() as connection:
        first, first_is_new = await request_gmail_action(connection, data)
    async with engine.begin() as connection:
        second, second_is_new = await request_gmail_action(connection, data)

    assert first_is_new is True
    assert second_is_new is False
    assert second.id == first.id

    outbox_key = f"command:{first.id}:requested"
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == outbox_key)
            )
        ).all()
    assert len(rows) == 1


async def test_concurrent_same_idempotency_key_creates_only_one_command() -> None:
    """[동시] unique constraint가 race의 loser를 DB level에서 reject한다.
    service는 error 대신 winner row를 반환하는 fallback으로 수렴한다."""
    key = str(uuid.uuid4())
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=account_id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=key,
        requested_by=user_id,
    )

    async def attempt():
        async with engine.begin() as connection:
            return await request_gmail_action(connection, data)

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(is_new for _, is_new in results) == [False, True]
    assert results[0][0].id == results[1][0].id


async def test_unsupported_action_type_raises_validation_error() -> None:
    data = await _make_input(action_type="delete_forever")

    with pytest.raises(ValidationError):
        async with engine.begin() as connection:
            await request_gmail_action(connection, data)


async def test_label_apply_without_gmail_label_id_raises_validation_error() -> None:
    data = await _make_input(action_type="label_apply", gmail_label_id=None)

    with pytest.raises(ValidationError):
        async with engine.begin() as connection:
            await request_gmail_action(connection, data)


async def test_other_workspace_account_raises_not_found() -> None:
    _, other_user_id, _ = await seed_scope()
    _, _, real_account_id = await seed_scope()
    message_id = await seed_message(real_account_id)
    data = RequestGmailActionInput(
        workspace_id=uuid.uuid4(),  # real_account_id를 소유한 workspace가 아님
        connected_account_id=real_account_id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=str(uuid.uuid4()),
        requested_by=other_user_id,
    )

    with pytest.raises(NotFoundError):
        async with engine.begin() as connection:
            await request_gmail_action(connection, data)


async def test_disconnecting_account_raises_conflict() -> None:
    workspace_id, user_id, account_id = await seed_scope(status="disconnecting")
    message_id = await seed_message(account_id)
    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=account_id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=str(uuid.uuid4()),
        requested_by=user_id,
    )

    with pytest.raises(ConflictError):
        async with engine.begin() as connection:
            await request_gmail_action(connection, data)


async def test_mutation_requires_command_row() -> None:
    """[선행조건] GmailMutationPort는 ledger row가 없는 임의의 command_id로
    호출될 수 없다. `apply()`는 command를 lookup하고 찾을 수 없는 것은 mutate하지 않는다."""
    mutator = FakeGmailMutationPort()

    with pytest.raises(NotFoundError):
        async with engine.begin() as connection:
            await mutator.apply(connection, command_id=uuid.uuid4())
