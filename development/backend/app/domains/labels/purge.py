"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

`label_correction_signals.message_id`는 NOT NULL이다(gmail_actions의 nullable message_id와
다름). purged message에 대한 signal은 dangling reference로 유지할 수 없으므로 null 처리하지
않고 row를 바로 delete한다. `rule_suggestions.correction_signal_id`도 NOT NULL이고 이 signal
row를 reference한다. 따라서 orchestration job(mail_sources.jobs.purge_disconnected_source)은
이 handler보다 먼저 assistant_decisions의 purge handler(rule_suggestions를 delete)를 실행해야
한다. 그렇지 않으면 이 delete가 foreign key violation으로 실패한다.

service_labels/gmail_label_mappings(label catalog 자체)는 db-schema.md 기준 ◆ content-bearing이
아니며 message content scope도 아니다. 따라서 건드리지 않는다(module-boundaries.md §8의
disconnect/purge flow는 labels catalog를 purge target으로 나열하지 않고, purged message
content에 묶인 correction-signal evidence만 나열한다).
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.labels.models import label_correction_signals


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    # local import로 __init__.py-time circular import를 피한다.
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
