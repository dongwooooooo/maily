"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

gmail_messages/message_excerpts are ◆ content-bearing (db-schema.md) —
purged on source disconnect. Runs LAST in the orchestration job's call
order (mail_sources.jobs.purge_disconnected_source): every other
domain's purge handler either deletes or nulls its own FK into
gmail_messages first, so this delete never hits a foreign key violation
from a row this module doesn't own.

message_excerpts/gmail_message_labels are this table's own children —
deleted here too (not ◆-marked individually, but they have no meaning
without the message and would themselves FK-block the gmail_messages
delete below).
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
