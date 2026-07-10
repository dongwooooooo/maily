"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

module-boundaries.md §8: assistant_decisions는 source content에 연결된 summaries/
proposals/rules를 purge한다. 여기의 모든 message-scoped table은 NOT NULL message_id FK를
가진다. null 처리하지 않고 바로 delete한다.

Ordering constraint(이 function이 아니라 orchestration job의 명시적 call order가 강제):
rule_suggestions.correction_signal_id는 labels.label_correction_signals에 대한 NOT NULL
FK이므로, labels의 purge handler가 그 signal row를 지우기 전에 이 handler가 반드시 먼저
실행되어야 한다. 그렇지 않으면 이 delete가 cascade할 대상을 남기지 못하고, labels는 여전히
이를 reference하는 rule_suggestions에 대한 자체 FK check에서 실패한다. 이 handler가
rule_suggestions를 먼저 지우는 이유는 labels의 후속 delete를 unblock하기 위해서다.

classification_rules는 workspace-level policy(service_label_id + match_condition, message/
account FK 없음)이므로 purge하지 않는다. source 하나를 disconnect해도 workspace가 다른
source에 계속 쓰려는 rule을 지우면 안 된다.
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
    # local import로 __init__.py-time circular import를 피한다.
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
