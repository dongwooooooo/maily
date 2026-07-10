from sqlalchemy import select

from app.core.database import engine
from app.domains.assistant_decisions.cleanup import prepare_cleanup_proposals
from app.domains.assistant_decisions.jobs.classify_importance import classify_importance_job
from app.domains.assistant_decisions.jobs.generate_summary import generate_summary_job
from app.domains.assistant_decisions.models import (
    cleanup_proposals,
    importance_jobs,
    message_importance_classifications,
    message_summaries,
    rule_suggestions,
    summary_jobs,
)
from app.domains.assistant_decisions.purge import purge_source
from app.domains.assistant_decisions.rules import create_rule_suggestion_from_signal
from app.domains.labels.models import label_correction_signals
from tests.domains.assistant_decisions.conftest import (
    seed_correction_signal,
    seed_message,
    seed_scope,
    seed_service_label,
)


async def _seed_full_content():
    workspace_id, user_id, account_id = await seed_scope(summary_enabled=True)
    message_id = await seed_message(account_id, sender="manager@example.com", snippet="본문")

    await generate_summary_job({"message_id": str(message_id)})
    await classify_importance_job({"message_id": str(message_id)})

    label_id = await seed_service_label(workspace_id, name="업무")
    signal_id = await seed_correction_signal(message_id=message_id, service_label_id=label_id, actor_id=user_id)
    async with engine.begin() as connection:
        await create_rule_suggestion_from_signal(connection, correction_signal_id=signal_id)

    async with engine.begin() as connection:
        await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )

    return account_id, message_id


async def test_purge_deletes_all_message_scoped_content() -> None:
    account_id, message_id = await _seed_full_content()

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        for table in (
            message_summaries,
            summary_jobs,
            message_importance_classifications,
            importance_jobs,
            cleanup_proposals,
        ):
            rows = (
                await connection.execute(select(table).where(table.c.message_id == message_id))
            ).mappings().all()
            assert rows == [], f"{table.name} not purged"

        suggestion_rows = (
            await connection.execute(
                select(rule_suggestions).where(
                    rule_suggestions.c.correction_signal_id.in_(
                        select(label_correction_signals.c.id).where(
                            label_correction_signals.c.message_id == message_id
                        )
                    )
                )
            )
        ).mappings().all()

    # correction signal itself is labels' own purge responsibility (see
    # tests/domains/labels/test_purge.py) — only rule_suggestions (this
    # domain's own table, referencing that signal) is asserted here.
    assert suggestion_rows == []


async def test_purge_no_content_is_noop() -> None:
    _workspace_id, _user_id, account_id = await seed_scope()
    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)
    # No exception — that's the assertion.


async def test_purge_only_affects_target_account() -> None:
    account_id, message_id = await _seed_full_content()
    other_account_id, other_message_id = await _seed_full_content()

    async with engine.begin() as connection:
        await purge_source(connection, source_id=account_id)

    async with engine.connect() as connection:
        purged = (
            await connection.execute(select(message_summaries).where(message_summaries.c.message_id == message_id))
        ).mappings().all()
        remaining = (
            await connection.execute(
                select(message_summaries).where(message_summaries.c.message_id == other_message_id)
            )
        ).mappings().all()

    assert purged == []
    assert len(remaining) == 1
