"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

module-boundaries.md §8: "gmail_actions keeps minimal activity audit" —
unlike briefing/mail_intake/assistant_decisions, gmail_actions does NOT
delete its rows on disconnect (gmail_action_commands/activity_logs/
undo_actions are not ◆ content-bearing in db-schema.md). The only purge
action here is releasing the FK: gmail_action_commands.message_id points
at gmail_messages, which mail_intake's own purge handler deletes — so
this must null that reference first (message_id is nullable, unlike
labels/assistant_decisions' NOT NULL message_id FKs, which must delete
instead — see those purge.py modules), or mail_intake's delete would
fail with a foreign key violation.

Filters directly on gmail_action_commands.connected_account_id (a column
this table already owns) rather than joining through gmail_messages —
gmail_actions has a hard architectural boundary (test_mutation_port_
boundary.py) forbidding any import of mail_intake, read/write path
separation from Task 9, so this can't look message ids up the way
labels/assistant_decisions' purge handlers do.
"""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.gmail_actions.models import gmail_action_commands


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    await connection.execute(
        update(gmail_action_commands)
        .where(gmail_action_commands.c.connected_account_id == source_id)
        .values(message_id=None)
    )
