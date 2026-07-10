"""IC2+IC3 (docs/goals/backend-plans/_build-schedule.md) — sync -> briefing,
sync -> assistant -> briefing 부분재생성. 둘 다 gmail_snapshot_changed를 producer로
공유하며 schedule의 "함께 배선" note에 따라 함께 wired된다.

Real chain이며 seeded shortcut은 없다. mail_sources.connect_gmail_source ->
mail_intake.sync_full(fake reader)이 gmail_snapshot_changed(workspace_id + message_ids)를
emit한다 -> dispatch가 이를 전체 list를 담은 build_briefing job 하나와 message별
generate_summary/classify_importance job으로 fan-out한다 -> 이 job들을 실행하면 실제
message_summaries/message_importance_classifications row가 생긴다 -> 두 job 자체의
summary_completed/importance_classified event가 두 번째 round의 message_id-scoped
build_briefing job을 dispatch한다 -> 최종 briefing_items projection은 어떤 trigger path가
먼저 도착했는지와 무관하게 둘 다 반영한다(briefing.md Job §동시).
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

    # 1차: gmail_snapshot_changed fan-out.
    async with engine.begin() as connection:
        round1_ids = await dispatch_pending_events(connection, consumers=ACTIVE_EVENT_CONSUMERS)
    async with engine.connect() as connection:
        round1_rows = (
            (await connection.execute(select(job_runs).where(job_runs.c.id.in_(round1_ids))))
            .mappings()
            .all()
        )
    # 이 dispatch call은 connect_gmail_source 자체의 gmail_source_connected event
    # (register_watch/sync_full, IC1 자체 test)도 처리한다. 또한 이 Postgres는 suite 전체에서
    # 공유되고 per-test rollback이 없으므로, 다른 test가 남긴 pending
    # gmail_snapshot_changed/summary_completed/importance_classified event도 처리될 수 있다.
    # 이 test의 message_ids를 참조하는 row로 엄격히 scope를 좁힌다.
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

    # 1차의 build_briefing job은 generate_summary/classify_importance 자체 job보다
    # 먼저 enqueue되고(따라서 이 test의 sequential loop에서도 먼저 실행됨), 이는 bug가 아니라
    # briefing.md의 "[선행조건] importance 결과가 아직 없는 상태" case다. projection row는
    # null summary/importance로 존재하고, 실제 data가 들어온 뒤 round 2의 message_id-scoped
    # rebuild가 실행되면 fresh하게 다시 파생된다(stale/overridden 아님).
    async with engine.connect() as connection:
        for message_id in message_ids:
            item = await briefing_repository.get_briefing_item_by_account_message(
                connection, connected_account_id=source.id, message_id=message_id
            )
            assert item is not None

    # 2차: generate_summary/classify_importance 자체의 summary_completed/
    # importance_classified event가 각각 message_id-scoped build_briefing job을 queue한다
    # (IC3의 "부분재생성").
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
    assert len(round2_this_test) == 4  # 2 messages x (summary_completed + importance_classified) 조합
    await _run_all_queued([r["id"] for r in round2_this_test])

    async with engine.connect() as connection:
        for message_id in message_ids:
            item = await briefing_repository.get_briefing_item_by_account_message(
                connection, connected_account_id=source.id, message_id=message_id
            )
            assert item["summary_text"] is not None
            assert item["importance_band"] is not None
