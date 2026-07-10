"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

module-boundaries.md §8: "gmail_actions keeps minimal activity audit" — briefing/
mail_intake/assistant_decisions와 달리 gmail_actions는 disconnect 때 row를 delete하지 않는다
(gmail_action_commands/activity_logs/undo_actions는 db-schema.md에서 ◆ content-bearing이 아님).
여기의 유일한 purge action은 FK release다. gmail_action_commands.message_id는 mail_intake의
purge handler가 delete하는 gmail_messages를 가리킨다. 따라서 먼저 이 reference를 null로
바꿔야 한다(message_id는 nullable. labels/assistant_decisions의 NOT NULL message_id FK는
대신 delete해야 함 — 해당 purge.py module 참고). 그렇지 않으면 mail_intake의 delete가
foreign key violation으로 실패한다.

gmail_messages를 통해 join하지 않고, 이 table이 이미 소유한 column인
gmail_action_commands.connected_account_id로 직접 filter한다. gmail_actions는 Task 9부터
read/write path separation을 위해 mail_intake import를 금지하는 hard architectural boundary를
갖는다(test_mutation_port_boundary.py). 따라서 labels/assistant_decisions의 purge handler처럼
message id를 lookup할 수 없다.
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
