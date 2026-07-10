from app.core.database import engine
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.jobs.prepare_cleanup_proposals import (
    prepare_cleanup_proposals_job,
)
from tests.domains.assistant_decisions.conftest import (
    seed_message,
    seed_message_labels,
    seed_scope,
)


async def test_job_wrapper_resolves_payload_and_delegates() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])

    await prepare_cleanup_proposals_job(
        {
            "workspace_id": str(workspace_id),
            "message_ids": [str(message_id)],
            "requested_by": str(user_id),
        }
    )

    async with engine.connect() as connection:
        count = await repository.count_cleanup_proposals_for_message(
            connection, message_id=message_id
        )
    assert count == 1


async def test_job_wrapper_no_message_ids_is_noop() -> None:
    workspace_id, user_id, _ = await seed_scope()

    await prepare_cleanup_proposals_job(
        {"workspace_id": str(workspace_id), "requested_by": str(user_id)}
    )
    # exception도 proposals도 없다. message_ids가 주어지지 않았으므로
    # message-scoped table에 대해 assert할 것이 없다.
