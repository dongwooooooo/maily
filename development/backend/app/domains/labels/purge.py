"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

`label_correction_signals.message_id` is NOT NULL (unlike gmail_actions'
nullable message_id) — a signal for a purged message can't be kept with
a dangling reference, so this deletes the row outright rather than
nulling it. `rule_suggestions.correction_signal_id` is also NOT NULL and
references these signal rows, so the orchestration job (mail_sources.
jobs.purge_disconnected_source) MUST run assistant_decisions' purge
handler (which deletes rule_suggestions) before this one, or this delete
fails on a foreign key violation.

service_labels/gmail_label_mappings (the label catalog itself) are not
◆ content-bearing per db-schema.md and aren't scoped to message content —
left untouched (module-boundaries.md §8's disconnect/purge flow doesn't
list labels' catalog as a purge target, only the correction-signal
evidence tied to purged message content).
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

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
    await connection.execute(
        delete(label_correction_signals).where(label_correction_signals.c.message_id.in_(message_ids))
    )
