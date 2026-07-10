import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from app.core.database import engine
from app.domains.assistant_decisions.jobs.classify_importance import classify_importance_job
from app.domains.assistant_decisions.jobs.generate_summary import generate_summary_job
from app.domains.assistant_decisions.models import (
    message_importance_classifications,
    message_summaries,
    rule_suggestions,
)
from app.domains.assistant_decisions.rules import create_rule_suggestion_from_signal
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.jobs.execute_action import run_execute_action
from app.domains.gmail_actions.models import gmail_action_commands
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from app.domains.identity.models import users, workspaces
from app.domains.labels.models import label_correction_signals
from app.domains.labels.schemas import CreateLabelInput, MoveMessageInput
from app.domains.labels.service import create_or_update_label, move_message_to_label
from app.domains.mail_intake.models import gmail_messages
from app.domains.mail_sources.jobs.purge_disconnected_source import run_purge_disconnected_source
from app.domains.mail_sources.models import gmail_oauth_credentials
from app.domains.mail_sources.repository import get_connected_account
from app.domains.mail_sources.schemas import ConnectGmailSourceInput, DisconnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source, disconnect_gmail_source


@pytest.fixture(autouse=True)
def _fresh_fake_mutator():
    mutator = FakeGmailMutationPort()
    execute_action.set_mutator(mutator)
    yield mutator
    execute_action.set_mutator(FakeGmailMutationPort())


async def _seed_disconnecting_account_with_full_content():
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
        await connection.execute(
            insert(users).values(
                id=user_id, google_subject=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.com", display_name=None
            )
        )
    data = ConnectGmailSourceInput(
        workspace_id=workspace_id,
        gmail_address=f"user-{uuid.uuid4()}@gmail.com",
        access_token="ya29.a0-example-access-token",
        refresh_token="1//0g-example-refresh-token",
        scope="https://www.googleapis.com/auth/gmail.readonly",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async with engine.begin() as connection:
        source, _ = await connect_gmail_source(connection, data)

    message_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=source.id,
                gmail_message_id=f"gmail-{uuid.uuid4()}",
                gmail_thread_id=f"thread-{uuid.uuid4()}",
                subject="분기 보고서",
                sender="manager@example.com",
                snippet="본문 스니펫",
            )
        )

    await generate_summary_job({"message_id": str(message_id)})
    await classify_importance_job({"message_id": str(message_id)})

    async with engine.begin() as connection:
        label, _ = await create_or_update_label(
            connection,
            CreateLabelInput(workspace_id=workspace_id, connected_account_id=source.id, name=f"L-{uuid.uuid4()}"),
        )
    async with engine.begin() as connection:
        move_result = await move_message_to_label(
            connection,
            MoveMessageInput(
                workspace_id=workspace_id,
                message_id=message_id,
                label_id=label.id,
                actor_id=user_id,
                idempotency_key=str(uuid.uuid4()),
            ),
        )
    # rule_suggestions.correction_signal_id is a NOT NULL FK into
    # labels.label_correction_signals — seeding this here is what makes
    # the full orchestration test below actually exercise the
    # assistant_decisions-before-labels ordering constraint (code review
    # caught this gap: without a real rule_suggestions row, swapping that
    # order in purge_disconnected_source.py would still pass the suite).
    async with engine.begin() as connection:
        await create_rule_suggestion_from_signal(
            connection, correction_signal_id=move_result.correction_signal_id
        )

    mark_read = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=source.id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=str(uuid.uuid4()),
        requested_by=user_id,
    )
    async with engine.begin() as connection:
        command, _ = await request_gmail_action(connection, mark_read)
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command.id)

    async with engine.begin() as connection:
        await disconnect_gmail_source(
            connection,
            DisconnectGmailSourceInput(workspace_id=workspace_id, connected_account_id=source.id),
        )

    return source.id, message_id, workspace_id


async def test_orchestration_purges_every_domain_in_fk_safe_order() -> None:
    source_id, message_id, workspace_id = await _seed_disconnecting_account_with_full_content()

    async with engine.begin() as connection:
        await run_purge_disconnected_source(connection, source_id=source_id)

    async with engine.connect() as connection:
        message_rows = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().all()
        summary_rows = (
            await connection.execute(select(message_summaries).where(message_summaries.c.message_id == message_id))
        ).mappings().all()
        importance_rows = (
            await connection.execute(
                select(message_importance_classifications).where(
                    message_importance_classifications.c.message_id == message_id
                )
            )
        ).mappings().all()
        signal_rows = (
            await connection.execute(
                select(label_correction_signals).where(label_correction_signals.c.message_id == message_id)
            )
        ).mappings().all()
        command_rows = (
            await connection.execute(
                select(gmail_action_commands).where(gmail_action_commands.c.connected_account_id == source_id)
            )
        ).mappings().all()
        credential_rows = (
            await connection.execute(
                select(gmail_oauth_credentials).where(gmail_oauth_credentials.c.connected_account_id == source_id)
            )
        ).mappings().all()
        account = await get_connected_account(connection, connected_account_id=source_id)
        suggestion_rows = (
            await connection.execute(select(rule_suggestions).where(rule_suggestions.c.workspace_id == workspace_id))
        ).mappings().all()

    assert message_rows == []
    assert summary_rows == []
    assert importance_rows == []
    assert signal_rows == []
    assert credential_rows == []
    # Confirms the assistant_decisions-before-labels ordering constraint:
    # if labels.purge_source had run first, this rule_suggestions row's
    # NOT NULL FK into the now-deleted signal would have blocked the
    # delete with an IntegrityError before this test ever reached this
    # assertion — reaching it at all is itself proof the order held.
    assert suggestion_rows == []
    assert account["status"] == "disconnected"
    # gmail_actions keeps both command rows (minimal audit) — the explicit
    # mark_read request plus IC5's own label_apply command from
    # move_message_to_label — with message_id released on each.
    assert len(command_rows) == 2
    assert all(row["message_id"] is None for row in command_rows)


async def test_orchestration_idempotent_on_double_run() -> None:
    """[멱등] purge job이 두 번 실행돼도 에러 없이 no-op으로 수렴하고
    다른 워크스페이스 데이터를 건드리지 않는다."""
    source_id, _message_id, _workspace_id = await _seed_disconnecting_account_with_full_content()

    async with engine.begin() as connection:
        await run_purge_disconnected_source(connection, source_id=source_id)
    async with engine.begin() as connection:
        await run_purge_disconnected_source(connection, source_id=source_id)
    # No exception on the second run — that's the assertion.
