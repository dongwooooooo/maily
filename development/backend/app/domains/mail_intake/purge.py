"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

gmail_messages/message_excerpts는 ◆ content-bearing(db-schema.md)이므로 source disconnect 시
purge된다. orchestration job의 call order(mail_sources.jobs.purge_disconnected_source)에서
LAST로 실행된다. 다른 모든 domain의 purge handler가 먼저 gmail_messages로 향하는 자체 FK를
delete하거나 null 처리하므로, 이 delete는 이 module이 소유하지 않는 row 때문에 foreign key
violation을 만나지 않는다.

message_excerpts/gmail_message_labels는 이 table의 own child다. 개별적으로 ◆ 표시되지는
않았지만 message 없이는 의미가 없고, 아래 gmail_messages delete를 FK로 막을 수 있으므로
여기서 함께 delete한다.
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.mail_intake.models import gmail_message_labels, gmail_messages, message_excerpts


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    message_ids = (
        await connection.execute(
            select(gmail_messages.c.id).where(gmail_messages.c.connected_account_id == source_id)
        )
    ).scalars().all()
    if not message_ids:
        return
    await connection.execute(
        delete(message_excerpts).where(message_excerpts.c.message_id.in_(message_ids))
    )
    await connection.execute(
        delete(gmail_message_labels).where(gmail_message_labels.c.message_id.in_(message_ids))
    )
    await connection.execute(delete(gmail_messages).where(gmail_messages.c.connected_account_id == source_id))
