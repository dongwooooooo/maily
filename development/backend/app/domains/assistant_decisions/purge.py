"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

module-boundaries.md §8: assistant_decisions purges summaries/proposals/
rules tied to source content. All message-scoped tables here have a
NOT NULL message_id FK — deleted outright, not nulled.

Ordering constraint (enforced by the orchestration job's explicit call
order, not by this function): rule_suggestions.correction_signal_id is a
NOT NULL FK into labels.label_correction_signals, so this handler MUST
run before labels' purge handler deletes those signal rows, or this
delete would leave nothing to cascade from (labels would then fail on
its own FK check against rule_suggestions still referencing it) — this
handler deletes rule_suggestions first specifically to unblock labels'
subsequent delete.

classification_rules is workspace-level policy (service_label_id +
match_condition, no message/account FK) — not purged; disconnecting one
source shouldn't erase rules a workspace still wants for other sources.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.assistant_decisions.models import (
    cleanup_proposals,
    importance_jobs,
    message_importance_classifications,
    message_summaries,
    rule_suggestions,
    summary_jobs,
)
from app.domains.labels.models import label_correction_signals


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    # Local import — avoids an __init__.py-time circular import.
    from app.domains.mail_intake.models import gmail_messages

    message_ids = (
        await connection.execute(
            select(gmail_messages.c.id).where(gmail_messages.c.connected_account_id == source_id)
        )
    ).scalars().all()
    if not message_ids:
        return

    signal_ids = (
        await connection.execute(
            select(label_correction_signals.c.id).where(
                label_correction_signals.c.message_id.in_(message_ids)
            )
        )
    ).scalars().all()
    if signal_ids:
        await connection.execute(
            delete(rule_suggestions).where(rule_suggestions.c.correction_signal_id.in_(signal_ids))
        )

    await connection.execute(delete(cleanup_proposals).where(cleanup_proposals.c.message_id.in_(message_ids)))
    await connection.execute(delete(message_summaries).where(message_summaries.c.message_id.in_(message_ids)))
    await connection.execute(delete(summary_jobs).where(summary_jobs.c.message_id.in_(message_ids)))
    await connection.execute(
        delete(message_importance_classifications).where(
            message_importance_classifications.c.message_id.in_(message_ids)
        )
    )
    await connection.execute(delete(importance_jobs).where(importance_jobs.c.message_id.in_(message_ids)))
