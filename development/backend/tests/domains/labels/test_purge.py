import uuid

from sqlalchemy import select

from app.core.database import engine
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.labels.models import label_correction_signals
from app.domains.labels.purge import purge_source
from app.domains.labels.schemas import CreateLabelInput, MoveMessageInput
from app.domains.labels.service import create_or_update_label, move_message_to_label
from app.domains.mail_intake.purge import purge_source as purge_mail_intake
from tests.domains.labels.conftest import seed_connected_account, seed_message, seed_user, seed_workspace


async def _seed_signal() -> tuple[uuid.UUID, uuid.UUID]:
    """실제 label_correction_signals row 하나와 함께 (source_id, message_id)를 반환한다."""
    execute_action.set_mutator(FakeGmailMutationPort())
    workspace_id = await seed_workspace()
    account_id = await seed_connected_account(workspace_id)
    user_id = await seed_user()
    message_id = await seed_message(account_id)
    async with engine.begin() as connection:
        label, _ = await create_or_update_label(
            connection,
            CreateLabelInput(workspace_id=workspace_id, connected_account_id=account_id, name=f"L-{uuid.uuid4()}"),
        )
    async with engine.begin() as connection:
        await move_message_to_label(
            connection,
            MoveMessageInput(
                workspace_id=workspace_id,
                message_id=message_id,
                label_id=label.id,
                actor_id=user_id,
                idempotency_key=str(uuid.uuid4()),
            ),
        )
    return account_id, message_id


async def test_purge_deletes_correction_signals() -> None:
    account_id, message_id = await _seed_signal()

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(label_correction_signals).where(label_correction_signals.c.message_id == message_id)
            )
        ).mappings().all()
    assert rows == []


async def test_purge_no_signals_is_noop() -> None:
    workspace_id = await seed_workspace()
    account_id = await seed_connected_account(workspace_id)
    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)
    # exception이 없는 것이 assertion이다.


async def test_purge_only_affects_target_account() -> None:
    account_id, message_id = await _seed_signal()
    other_account_id, other_message_id = await _seed_signal()

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        purged = (
            await connection.execute(
                select(label_correction_signals).where(label_correction_signals.c.message_id == message_id)
            )
        ).mappings().all()
        remaining = (
            await connection.execute(
                select(label_correction_signals).where(label_correction_signals.c.message_id == other_message_id)
            )
        ).mappings().all()

    assert purged == []
    assert len(remaining) == 1


async def test_purge_unblocks_mail_intake_message_delete() -> None:
    """[선행조건] label_correction_signals가 message_id를 NOT NULL FK로
    참조하므로, labels가 먼저 지우지 않으면 mail_intake의 gmail_messages
    delete가 FK violation으로 실패한다 — 순서 보장 실증. move_message_to_label
    이 IC5에서 gmail_actions label_apply command도 함께 만들므로(message_id
    FK), 정본 오케스트레이션 순서대로 gmail_actions 먼저 purge한다."""
    from app.domains.gmail_actions.purge import purge_source as purge_gmail_actions

    account_id, _message_id = await _seed_signal()

    async with engine.begin() as connection:
        await purge_gmail_actions(connection, source_id=account_id)
        await purge_source(connection, source_id=account_id)
        await purge_mail_intake(connection, source_id=account_id)
    # FK violation이 발생하지 않는 것이 assertion이다.
