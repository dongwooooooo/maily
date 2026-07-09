import uuid

from sqlalchemy import select

from app.core.database import engine
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.jobs.generate_summary import generate_summary_job
from app.domains.assistant_decisions.llm import SummaryInput
from app.domains.assistant_decisions.models import summary_jobs
from app.domains.assistant_decisions.summaries import run_generate_summary
from tests.domains.assistant_decisions.conftest import (
    seed_message,
    seed_message_excerpt,
    seed_scope,
)


async def test_job_wrapper_resolves_message_id_and_delegates() -> None:
    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(account_id, snippet="본문 스니펫")

    await generate_summary_job({"message_id": str(message_id)})

    async with engine.connect() as connection:
        summary = await repository.get_message_summary(connection, message_id=message_id)
    assert summary is not None
    assert summary["is_metadata_only"] is False


async def test_rerun_upserts_single_row_not_duplicate() -> None:
    """[멱등] assistant_decisions.md "같은 message 재실행은 upsert라 row
    하나만 유지" — 두 번 실행해도 message_summaries에 message_id당 row가
    하나만 남고 version만 올라간다."""
    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(account_id, snippet="본문 스니펫")

    await generate_summary_job({"message_id": str(message_id)})
    await generate_summary_job({"message_id": str(message_id)})

    async with engine.connect() as connection:
        from app.domains.assistant_decisions.models import message_summaries

        rows = (
            (
                await connection.execute(
                    select(message_summaries).where(message_summaries.c.message_id == message_id)
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1
    assert rows[0]["summary_version"] == 2


async def test_llm_payload_allows_only_metadata_fields() -> None:
    """[데이터경계] The payload handed to the LLM port is built exclusively
    from SummaryInput's fixed field set — subject/sender/snippet/labels/
    excerpt. There is no code path here that could add a body/prompt key."""
    assert set(SummaryInput.__annotations__.keys()) == {
        "subject",
        "sender",
        "snippet",
        "labels",
        "excerpt",
    }

    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(
        account_id, subject="공지", sender="ops@example.com", snippet="본문 스니펫"
    )
    await seed_message_excerpt(message_id, "짧은 발췌문")

    async with engine.begin() as connection:
        from app.domains.assistant_decisions import service

        message = await service.get_message_or_404(connection, message_id=message_id)
        payload = await service.build_summary_payload(connection, message=message)

    assert set(payload.keys()) == {"subject", "sender", "snippet", "labels", "excerpt"}
    assert payload["excerpt"] == "짧은 발췌문"


async def test_llm_failure_marks_job_failed_without_writing_summary(_fresh_fake_llm) -> None:
    """[부분실패] LLM 호출 실패 -> job failed, attempt_count+1, no
    message_summaries row written, no event emitted."""
    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(account_id, snippet="본문 스니펫")
    _fresh_fake_llm.fail_next_summarize()

    async with engine.begin() as connection:
        result = await run_generate_summary(connection, message_id=message_id)

    assert result is None
    async with engine.connect() as connection:
        summary = await repository.get_message_summary(connection, message_id=message_id)
        job_row = (
            await connection.execute(
                select(summary_jobs).where(summary_jobs.c.message_id == message_id)
            )
        ).mappings().first()

    assert summary is None
    assert job_row["status"] == "failed"
    assert job_row["attempt_count"] == 1


async def test_missing_message_snapshot_rejects_job() -> None:
    """[선행조건] message snapshot 부재 -> job 거부(NotFoundError)."""
    from app.core.errors import NotFoundError

    missing_message_id = uuid.uuid4()
    async with engine.begin() as connection:
        try:
            await run_generate_summary(connection, message_id=missing_message_id)
            assert False, "expected NotFoundError"
        except NotFoundError:
            pass
