from sqlalchemy import select

from app.core.database import engine
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.importance import run_classify_importance, to_public_view
from app.domains.assistant_decisions.models import message_importance_classifications
from app.domains.assistant_decisions.summaries import run_generate_summary
from tests.domains.assistant_decisions.conftest import seed_message, seed_scope


async def test_pending_is_absent_row_not_flag() -> None:
    """흐름 2: 판단 전 상태는 row 부재로 표현 — 별도 pending 컬럼 없음."""
    async with engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_conn: [
                c["name"]
                for c in __import__("sqlalchemy").inspect(sync_conn).get_columns(
                    "message_importance_classifications"
                )
            ]
        )
    assert "pending" not in [c.lower() for c in columns]
    assert "is_pending" not in [c.lower() for c in columns]

    _, _, account_id = await seed_scope()
    message_id = await seed_message(account_id)
    async with engine.connect() as connection:
        row = await repository.get_message_importance_classification(
            connection, message_id=message_id
        )
    assert row is None


async def test_band_and_reason_persisted() -> None:
    _, _, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=False)

    async with engine.begin() as connection:
        result = await run_classify_importance(connection, message_id=message_id)

    assert result["importance_band"] in {"urgent", "normal", "low"}
    assert result["reason"]
    assert result["classification_version"] == 1

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(message_importance_classifications).where(
                    message_importance_classifications.c.message_id == message_id
                )
            )
        ).mappings().first()
    assert row is not None
    assert row["importance_band"] == result["importance_band"]


async def test_reason_hidden_by_default() -> None:
    _, _, account_id = await seed_scope()
    message_id = await seed_message(account_id)

    async with engine.begin() as connection:
        result = await run_classify_importance(connection, message_id=message_id)

    default_view = to_public_view(result)
    assert "reason" not in default_view

    full_view = to_public_view(result, include_reason=True)
    assert full_view["reason"] == result["reason"]


async def test_importance_independent_of_summary() -> None:
    """summary_enabled=False (no summary job created at all) -> importance
    classification still runs and succeeds — the two jobs never gate each
    other."""
    _, _, account_id = await seed_scope(summary_enabled=False)
    message_id = await seed_message(account_id, snippet="본문 스니펫")

    async with engine.begin() as connection:
        summary_result = await run_generate_summary(connection, message_id=message_id)
    async with engine.begin() as connection:
        importance_result = await run_classify_importance(connection, message_id=message_id)

    assert summary_result is None  # no job created, per privacy contract
    assert importance_result is not None
    assert importance_result["importance_band"] in {"urgent", "normal", "low"}
