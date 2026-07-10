from sqlalchemy import inspect, select

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.models import summary_jobs
from app.domains.assistant_decisions.summaries import run_generate_summary
from tests.domains.assistant_decisions.conftest import seed_message, seed_scope

_FORBIDDEN_SUBSTRINGS = ("body", "prompt", "raw_")


async def test_raw_body_and_prompt_never_persisted() -> None:
    """G6 structural check: neither summary_jobs nor message_summaries has
    a column that could hold a raw email body or a raw LLM prompt."""
    async with engine.connect() as connection:
        summary_job_columns = await connection.run_sync(
            lambda sync_conn: [c["name"] for c in inspect(sync_conn).get_columns("summary_jobs")]
        )
        message_summary_columns = await connection.run_sync(
            lambda sync_conn: [
                c["name"] for c in inspect(sync_conn).get_columns("message_summaries")
            ]
        )

    for column_name in summary_job_columns + message_summary_columns:
        lowered = column_name.lower()
        assert not any(forbidden in lowered for forbidden in _FORBIDDEN_SUBSTRINGS), column_name


async def test_summary_off_makes_no_job() -> None:
    """[선행조건] summary_enabled=False -> no summary_jobs row is created at
    all (not just skipped-with-a-row)."""
    _, _, account_id = await seed_scope(summary_enabled=False)
    message_id = await seed_message(account_id, snippet="분기 실적 요약을 첨부드립니다.")

    async with engine.begin() as connection:
        result = await run_generate_summary(connection, message_id=message_id)

    assert result is None
    async with engine.connect() as connection:
        summary_row = await repository.get_message_summary(connection, message_id=message_id)
        job_rows = (
            await connection.execute(
                select(summary_jobs).where(summary_jobs.c.message_id == message_id)
            )
        ).all()
    assert summary_row is None
    assert job_rows == []


async def test_metadata_only_fallback() -> None:
    """summary_enabled=True but no snippet to summarize from -> job still
    succeeds, but is_metadata_only=True and summary_text falls back to the
    subject line (LLM 없이 subject 기반 요약 대체) instead of failing."""
    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(account_id, subject="공지: 정기 점검 안내", snippet=None)

    async with engine.begin() as connection:
        result = await run_generate_summary(connection, message_id=message_id)

    assert result is not None
    assert result["is_metadata_only"] is True
    assert result["summary_text"] == "공지: 정기 점검 안내"


async def test_summary_completed_emitted_with_version() -> None:
    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(
        account_id, subject="분기 보고서", snippet="이번 분기 실적 요약을 첨부드립니다."
    )

    async with engine.begin() as connection:
        result = await run_generate_summary(connection, message_id=message_id)

    assert result["is_metadata_only"] is False
    assert result["summary_version"] == 1

    key = f"message:{message_id}:summary:1"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()
    assert row is not None
    assert row["event_type"] == "summary_completed"
