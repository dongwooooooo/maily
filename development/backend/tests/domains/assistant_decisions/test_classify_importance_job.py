import uuid

from sqlalchemy import select

from app.core.database import engine
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.jobs.classify_importance import classify_importance_job
from app.domains.assistant_decisions.jobs.generate_summary import generate_summary_job
from app.domains.assistant_decisions.llm import ImportanceInput
from app.domains.assistant_decisions.models import importance_jobs
from app.domains.assistant_decisions.importance import run_classify_importance
from tests.domains.assistant_decisions.conftest import seed_message, seed_scope


async def test_job_wrapper_resolves_message_id_and_delegates() -> None:
    _, _, account_id = await seed_scope()
    message_id = await seed_message(account_id)

    await classify_importance_job({"message_id": str(message_id)})

    async with engine.connect() as connection:
        classification = await repository.get_message_importance_classification(
            connection, message_id=message_id
        )
    assert classification is not None


async def test_rerun_upserts_single_row_not_duplicate() -> None:
    """[멱등] 같은 message로 두 번 실행해도 message_importance_classifications에
    row 하나만 남고 classification_version만 올라간다."""
    _, _, account_id = await seed_scope()
    message_id = await seed_message(account_id)

    await classify_importance_job({"message_id": str(message_id)})
    await classify_importance_job({"message_id": str(message_id)})

    async with engine.connect() as connection:
        from app.domains.assistant_decisions.models import message_importance_classifications

        rows = (
            (
                await connection.execute(
                    select(message_importance_classifications).where(
                        message_importance_classifications.c.message_id == message_id
                    )
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1
    assert rows[0]["classification_version"] == 2


async def test_llm_payload_allows_only_metadata_fields() -> None:
    assert set(ImportanceInput.__annotations__.keys()) == {
        "subject",
        "sender",
        "snippet",
        "labels",
        "is_read",
    }


async def test_llm_failure_marks_job_failed_without_writing_classification(
    _fresh_fake_llm,
) -> None:
    _, _, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    _fresh_fake_llm.fail_next_classify_importance()

    async with engine.begin() as connection:
        result = await run_classify_importance(connection, message_id=message_id)

    assert result is None
    async with engine.connect() as connection:
        classification = await repository.get_message_importance_classification(
            connection, message_id=message_id
        )
        job_row = (
            await connection.execute(
                select(importance_jobs).where(importance_jobs.c.message_id == message_id)
            )
        ).mappings().first()

    assert classification is None
    assert job_row["status"] == "failed"
    assert job_row["attempt_count"] == 1


async def test_missing_message_snapshot_rejects_job() -> None:
    from app.core.errors import NotFoundError

    missing_message_id = uuid.uuid4()
    async with engine.begin() as connection:
        try:
            await run_classify_importance(connection, message_id=missing_message_id)
            assert False, "expected NotFoundError"
        except NotFoundError:
            pass


async def test_classify_importance_independent_of_generate_summary_job_failure(
    _fresh_fake_llm,
) -> None:
    """[동시]/[부분실패] generate_summary failing (or being skipped) never
    blocks classify_importance for the same message, run through the real
    job wrappers this time (not the bare service functions)."""
    _, _, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(account_id, snippet="본문 스니펫")
    _fresh_fake_llm.fail_next_summarize()

    await generate_summary_job({"message_id": str(message_id)})
    await classify_importance_job({"message_id": str(message_id)})

    async with engine.connect() as connection:
        summary = await repository.get_message_summary(connection, message_id=message_id)
        classification = await repository.get_message_importance_classification(
            connection, message_id=message_id
        )
    assert summary is None  # summary job failed, no row written
    assert classification is not None  # importance unaffected
