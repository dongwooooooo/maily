import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.briefing.jobs.build_briefing import build_briefing_job
from app.domains.briefing.jobs.reactivate_reminders import reactivate_reminders_job
from app.domains.briefing.router import router as router

JOB_HANDLERS: dict = {
    "build_briefing": build_briefing_job,
    "reactivate_reminders": reactivate_reminders_job,
}

# _integration-contract.md §3 — 이 domain이 consume하는 각 event마다 어떤 job이 queue되는지
# 나타낸다. outbox dispatcher가 실제로 이를 호출하도록 wiring하는 작업(IC2/IC3)은 이후
# coordinator step이다. coordinator가 job docstring에서 역추적하지 않도록 지금 contract table에
# 따른 intended wiring을 이 map에 문서화한다.
EVENT_CONSUMERS: dict = {
    "gmail_snapshot_changed": ["build_briefing"],
    "gmail_action_applied": ["build_briefing"],
    "gmail_action_undone": ["build_briefing"],
    "summary_completed": ["build_briefing"],
    "importance_classified": ["build_briefing"],
    "reminder_reactivated": ["build_briefing"],
    # module-boundaries.md / assistant_decisions.md는 briefing을 notifications와 함께
    # cleanup_proposal_created consumer로 나열한다. 이 worktree의 original trigger count에서는
    # 빠졌고 integration 때 추가됐다.
    "cleanup_proposal_created": ["build_briefing"],
}


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    """PURGE_HANDLER(source_id) — _integration-contract.md §4.

    briefing_items/briefing_item_states는 content-bearing(◆, db-schema.md)이므로 source
    disconnect 시 purge된다(briefing.md "워크트리 격리 노트"). briefing_item_states에는
    connected_account_id column이 없다(durable state는 의도적으로 gmail_messages만 reference,
    models.py 참고). 따라서 purge는 account의 state row를 찾기 위해 gmail_messages를 통해
    join하고, reminders는 briefing_item_state_id를 통해 cascade된다.
    """
    from app.domains.briefing.models import briefing_item_states, briefing_items, reminders
    from app.domains.mail_intake.models import gmail_messages

    await connection.execute(
        delete(briefing_items).where(briefing_items.c.connected_account_id == source_id)
    )

    state_ids = (
        await connection.execute(
            select(briefing_item_states.c.id)
            .select_from(
                briefing_item_states.join(
                    gmail_messages, gmail_messages.c.id == briefing_item_states.c.message_id
                )
            )
            .where(gmail_messages.c.connected_account_id == source_id)
        )
    ).scalars().all()
    if state_ids:
        await connection.execute(
            delete(reminders).where(reminders.c.briefing_item_state_id.in_(state_ids))
        )
        await connection.execute(
            delete(briefing_item_states).where(briefing_item_states.c.id.in_(state_ids))
        )


PURGE_HANDLER = purge_source
