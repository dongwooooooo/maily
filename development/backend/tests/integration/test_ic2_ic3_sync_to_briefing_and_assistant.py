"""IC2+IC3 (docs/goals/backend-plans/_build-schedule.md) — sync -> briefing,
sync -> assistant -> briefing 부분재생성. Both share gmail_snapshot_changed
as producer, wired together per the schedule's "함께 배선" note.

Real chain, no seeded shortcuts: mail_sources.connect_gmail_source ->
mail_intake.sync_full (fake reader) emits gmail_snapshot_changed
(workspace_id + message_ids) -> dispatch fans that out to one
build_briefing job (whole list) plus one generate_summary/
classify_importance job per message -> running those produces real
message_summaries/message_importance_classifications rows -> those two
jobs' own summary_completed/importance_classified events dispatch a
second round of (message_id-scoped) build_briefing jobs -> the final
briefing_items projection reflects both, regardless of which trigger
path got there first (briefing.md Job §동시).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from app.core.database import engine
from app.core.discovery import register_discovered_jobs
from app.core.jobs import registry
from app.core.jobs.dispatcher import run_job
from app.core.jobs.models import job_runs
from app.core.jobs.outbox_dispatcher import dispatch_pending_events
from app.core.jobs.wiring import ACTIVE_EVENT_CONSUMERS
from app.domains.assistant_decisions.fake_llm import FakeAssistantLLM
from app.domains.assistant_decisions.llm import set_llm
from app.domains.briefing import repository as briefing_repository
from app.domains.identity.models import workspaces
from app.domains.mail_intake import service as mail_intake_service
from app.domains.mail_intake.fake_reader import FakeGmailReader, FakeMessage
from app.domains.mail_intake.gmail_reader import set_reader
from app.domains.mail_sources.schemas import ConnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source


async def _seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


@pytest.fixture(autouse=True)
def _registered_jobs():
    register_discovered_jobs()
    yield
    registry.clear()


async def _run_all_queued(job_ids: list[uuid.UUID]) -> None:
    for job_id in job_ids:
        async with engine.begin() as connection:
            status = await run_job(connection, job_id=job_id, worker_id="ic2-ic3-test")
        assert status == "succeeded"


async def test_snapshot_changed_fans_out_to_briefing_and_assistant_and_converges() -> None:
    workspace_id = await _seed_workspace()
    data = ConnectGmailSourceInput(
        workspace_id=workspace_id,
        gmail_address=f"user-{uuid.uuid4()}@gmail.com",
        access_token="ya29.a0-example-access-token",
        refresh_token="1//0g-example-refresh-token",
        scope="https://www.googleapis.com/auth/gmail.readonly",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    async with engine.begin() as connection:
        source, _is_new = await connect_gmail_source(connection, data)

    reader = FakeGmailReader()
    reader.seed_mailbox(
        source.id,
        messages=[
            FakeMessage(
                gmail_message_id="msg-ic2-1",
                gmail_thread_id="thread-ic2-1",
                subject="분기 정산 안내",
                snippet="이번 분기 정산 관련 안내드립니다",
            ),
            FakeMessage(
                gmail_message_id="msg-ic2-2",
                gmail_thread_id="thread-ic2-2",
                subject="회의 일정 변경",
                snippet="다음 주 회의 일정이 변경되었습니다",
            ),
        ],
        history_id=7,
    )
    set_reader(reader)
    set_llm(FakeAssistantLLM())

    async with engine.begin() as connection:
        result = await mail_intake_service.sync_full(
            connection, connected_account_id=source.id, reason="initial"
        )
    message_ids = set(result["message_ids"])
    assert len(message_ids) == 2

    # Round 1: gmail_snapshot_changed fans out.
    async with engine.begin() as connection:
        round1_ids = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        round1_rows = (
            (await connection.execute(select(job_runs).where(job_runs.c.id.in_(round1_ids))))
            .mappings()
            .all()
        )
    # This dispatch call also processes: connect_gmail_source's own
    # gmail_source_connected event (register_watch/sync_full, IC1's own
    # test), and — since this Postgres is shared across the whole suite
    # with no per-test rollback — any leftover pending gmail_snapshot_
    # changed/summary_completed/importance_classified events other tests
    # left behind. Scope strictly to rows that reference this test's own
    # message_ids.
    str_message_ids = {str(m) for m in message_ids}

    def _for_this_test(row: dict) -> bool:
        payload = row["payload"]
        if row["job_type"] == "build_briefing":
            return bool(set(payload.get("message_ids", [])) & str_message_ids)
        return payload.get("message_id") in str_message_ids

    round1_this_source = [r for r in round1_rows if _for_this_test(r)]
    round1_job_types = sorted(r["job_type"] for r in round1_this_source)
    assert round1_job_types == sorted(
        ["build_briefing"] + ["generate_summary"] * 2 + ["classify_importance"] * 2
    )
    await _run_all_queued([r["id"] for r in round1_this_source])

    # Round 1's build_briefing job is enqueued (and so runs, in this test's
    # sequential loop) before generate_summary/classify_importance's own
    # jobs — this is the "[선행조건] importance 결과가 아직 없는 상태" case
    # from briefing.md, not a bug: the projection row exists with null
    # summary/importance, re-derived fresh (not stale/overridden) once
    # round 2's message_id-scoped rebuild runs after the real data lands.
    async with engine.connect() as connection:
        for message_id in message_ids:
            item = await briefing_repository.get_briefing_item_by_account_message(
                connection, connected_account_id=source.id, message_id=message_id
            )
            assert item is not None

    # Round 2: generate_summary/classify_importance's own summary_completed/
    # importance_classified events each queue a message_id-scoped
    # build_briefing job (IC3's "부분재생성").
    async with engine.begin() as connection:
        round2_ids = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        round2_rows = (
            (await connection.execute(select(job_runs).where(job_runs.c.id.in_(round2_ids))))
            .mappings()
            .all()
        )
    round2_this_test = [
        r
        for r in round2_rows
        if r["job_type"] == "build_briefing"
        and set(r["payload"].get("message_ids", [])) & {str(m) for m in message_ids}
    ]
    assert len(round2_this_test) == 4  # 2 messages x (summary_completed + importance_classified)
    await _run_all_queued([r["id"] for r in round2_this_test])

    async with engine.connect() as connection:
        for message_id in message_ids:
            item = await briefing_repository.get_briefing_item_by_account_message(
                connection, connected_account_id=source.id, message_id=message_id
            )
            assert item["summary_text"] is not None
            assert item["importance_band"] is not None
