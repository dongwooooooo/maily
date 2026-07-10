"""IC4 (docs/goals/backend-plans/_build-schedule.md) — action ledger.

gmail_actions.request_gmail_action(real producer)이 gmail_action_requested를 emit한다
-> dispatch가 execute_action을 queue한다 -> 이를 실행하면 fake mutation이 적용되고
gmail_action_applied를 emit한다(이 IC에서 추가된 workspace_id/message_id/label delta 포함)
-> dispatch가 이를 build_briefing(message-scoped rebuild)과 mail_intake의 reconcile_action
(_build-schedule.md가 명시적으로 부르는 "snapshot reconcile")으로 fan-out한다 -> 둘 다
반영된다. sync tick을 기다리지 않고 gmail_messages.is_read가 local에서 바뀌고,
briefing_items는 done state를 반영한다.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.core.jobs import registry
from app.core.jobs.dispatcher import run_job
from app.core.jobs.models import job_runs
from app.core.jobs.outbox_dispatcher import dispatch_pending_events
from app.core.jobs.wiring import ACTIVE_EVENT_CONSUMERS
from app.domains.briefing import repository as briefing_repository
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.jobs import execute_action
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from app.domains.mail_intake.models import gmail_messages
from tests.domains.gmail_actions.conftest import seed_message, seed_scope


@pytest.fixture(autouse=True)
def _fresh_fake_mutator():
    mutator = FakeGmailMutationPort()
    execute_action.set_mutator(mutator)
    yield mutator
    execute_action.set_mutator(FakeGmailMutationPort())


@pytest.fixture(autouse=True)
def _registered_jobs():
    from app.core.discovery import register_discovered_jobs

    register_discovered_jobs()
    yield
    registry.clear()


async def _run_all(job_ids: list[uuid.UUID]) -> None:
    for job_id in job_ids:
        async with engine.begin() as connection:
            status = await run_job(connection, job_id=job_id, worker_id="ic4-test")
        assert status == "succeeded"


async def _dispatch_relevant(*, command_id: uuid.UUID, message_id: uuid.UUID) -> list[dict]:
    async with engine.begin() as connection:
        ids = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        rows = (await connection.execute(select(job_runs).where(job_runs.c.id.in_(ids)))).mappings().all()
    return [
        r
        for r in rows
        if r["payload"].get("command_id") == str(command_id)
        or r["payload"].get("message_id") == str(message_id)
        or str(message_id) in r["payload"].get("message_ids", [])
    ]


async def test_mark_read_action_reconciles_snapshot_and_rebuilds_briefing() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    execute_action.get_mutator().seed_labels(message_id, {"UNREAD", "INBOX"})

    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=account_id,
        message_id=message_id,
        action_type="mark_read",
        idempotency_key=str(uuid.uuid4()),
        requested_by=user_id,
    )
    async with engine.begin() as connection:
        command, _is_new = await request_gmail_action(connection, data)

    # 1차: gmail_action_requested -> execute_action.
    round1 = await _dispatch_relevant(command_id=command.id, message_id=message_id)
    assert [r["job_type"] for r in round1] == ["execute_action"]
    await _run_all([r["id"] for r in round1])

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
    assert row["is_read"] is False  # 아직 reconciled 아님 — 2차에서 처리

    # 2차: gmail_action_applied -> build_briefing + reconcile_action.
    round2 = await _dispatch_relevant(command_id=command.id, message_id=message_id)
    assert sorted(r["job_type"] for r in round2) == ["build_briefing", "reconcile_action"]
    await _run_all([r["id"] for r in round2])

    async with engine.connect() as connection:
        row = (
            await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
        ).mappings().first()
        item = await briefing_repository.get_briefing_item_by_account_message(
            connection, connected_account_id=account_id, message_id=message_id
        )

    assert row["is_read"] is True
    assert item is not None
