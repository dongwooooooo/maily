"""IC5 (docs/goals/backend-plans/_build-schedule.md) — labels 이동 → action·rule.

Two independent wirings share `move_message_to_label` as producer:

1. label apply command — NOT dispatcher-wired. labels.service.
   move_message_to_label calls gmail_actions.request_gmail_action
   directly and synchronously (labels.md §73) — verified here without
   going through the outbox dispatcher at all.
2. label_correction_recorded -> create_rule_suggestions — dispatcher-wired
   (wiring.py), verified through the real dispatch/run_job path.

IC6 (cleanup 승인→action) needs no new wiring — assistant_decisions.
cleanup.approve_cleanup_proposal already calls request_gmail_action
directly and is already covered end-to-end (against the real gmail_actions
module) by tests/domains/assistant_decisions/test_cleanup_review.py.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert, select

from app.core.database import engine
from app.core.discovery import register_discovered_jobs
from app.core.jobs import registry
from app.core.jobs.dispatcher import run_job
from app.core.jobs.models import job_runs
from app.core.jobs.outbox_dispatcher import dispatch_pending_events
from app.core.jobs.wiring import ACTIVE_EVENT_CONSUMERS
from app.domains.assistant_decisions.models import rule_suggestions
from app.domains.gmail_actions.models import gmail_action_commands
from app.domains.identity.models import users, workspaces
from app.domains.labels.models import gmail_label_mappings, service_labels
from app.domains.labels.schemas import MoveMessageInput
from app.domains.labels.service import move_message_to_label
from app.domains.mail_intake.models import gmail_messages
from app.domains.mail_sources.models import connected_gmail_accounts


@pytest.fixture(autouse=True)
def _registered_jobs():
    register_discovered_jobs()
    yield
    registry.clear()


async def _seed_scope() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
        await connection.execute(
            insert(users).values(
                id=user_id,
                google_subject=str(uuid.uuid4()),
                email=f"{uuid.uuid4()}@example.com",
                display_name=None,
            )
        )
        await connection.execute(
            insert(connected_gmail_accounts).values(
                id=account_id,
                workspace_id=workspace_id,
                gmail_address=f"user-{uuid.uuid4()}@gmail.com",
                display_name=None,
                status="connected",
                version=0,
                connected_at=datetime.now(timezone.utc),
            )
        )
    return workspace_id, user_id, account_id


async def _seed_message(account_id: uuid.UUID, *, sender: str) -> uuid.UUID:
    message_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(gmail_messages).values(
                id=message_id,
                connected_account_id=account_id,
                gmail_message_id=f"gmail-{uuid.uuid4()}",
                gmail_thread_id=f"thread-{uuid.uuid4()}",
                sender=sender,
            )
        )
    return message_id


async def _seed_label(workspace_id: uuid.UUID, account_id: uuid.UUID) -> uuid.UUID:
    label_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with engine.begin() as connection:
        await connection.execute(
            insert(service_labels).values(
                id=label_id,
                workspace_id=workspace_id,
                name="업무",
                hidden=False,
                order_index=0,
                updated_at=now,
            )
        )
        await connection.execute(
            insert(gmail_label_mappings).values(
                id=uuid.uuid4(),
                service_label_id=label_id,
                connected_account_id=account_id,
                gmail_label_id=None,
                gmail_label_name="Maily/업무",
            )
        )
    return label_id


async def test_move_requests_label_apply_command_and_rule_suggestion_via_dispatch() -> None:
    workspace_id, user_id, account_id = await _seed_scope()
    message_id = await _seed_message(account_id, sender="notices@example.com")
    label_id = await _seed_label(workspace_id, account_id)

    async with engine.begin() as connection:
        result = await move_message_to_label(
            connection,
            MoveMessageInput(
                workspace_id=workspace_id,
                message_id=message_id,
                label_id=label_id,
                actor_id=user_id,
                idempotency_key=str(uuid.uuid4()),
            ),
        )

    # 1. Direct synchronous call — no dispatch needed for this half.
    async with engine.connect() as connection:
        command_rows = (
            await connection.execute(
                select(gmail_action_commands).where(
                    gmail_action_commands.c.message_id == message_id
                )
            )
        ).mappings().all()
    assert len(command_rows) == 1
    assert command_rows[0]["action_type"] == "label_apply"
    assert command_rows[0]["payload"]["add_label_ids"] == ["Maily/업무"]

    # 2. Dispatcher half: label_correction_recorded -> create_rule_suggestions.
    async with engine.begin() as connection:
        enqueued = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        rows = (await connection.execute(select(job_runs).where(job_runs.c.id.in_(enqueued)))).mappings().all()
    relevant = [r for r in rows if r["payload"].get("correction_signal_id") == str(result.correction_signal_id)]
    assert [r["job_type"] for r in relevant] == ["create_rule_suggestions"]

    for row in relevant:
        async with engine.begin() as connection:
            status = await run_job(connection, job_id=row["id"], worker_id="ic5-test")
        assert status == "succeeded"

    async with engine.connect() as connection:
        suggestion_rows = (
            await connection.execute(
                select(rule_suggestions).where(
                    rule_suggestions.c.correction_signal_id == result.correction_signal_id
                )
            )
        ).mappings().all()
    assert len(suggestion_rows) == 1
    assert suggestion_rows[0]["suggested_condition"] == {"sender": "notices@example.com"}
