"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

orchestration job의 call order에서 마지막으로 실행된다. 이 시점에는 다른 모든 domain의
message-scoped content가 사라져 있다(mail_intake의 purge_source가 방금 실행되어 gmail_messages
자체를 delete). 따라서 mail_sources 자체의 disconnect-time-deferred step 두 개만 끝내면 된다.
◆ content-bearing credential ciphertext를 완전히 제거하고(disconnect_gmail_source는 빠른
synchronous marker로 revoked_at만 설정했고, 이것이 실제 purge), account를 terminal
`disconnected` status로 전환한다. `connected_gmail_accounts` 자체는 유지한다(delete하지 않음).
module-boundaries.md §8의 "최소 audit 보존"(minimal audit retention)이다.

[멱등] `connected_gmail_accounts` row는 절대 delete되지 않으므로 `account is None`은
retried purge가 아니라 존재하지 않거나 이미 hard-delete된 source_id만 guard한다. 실제 idempotency
guard는 아래의 명시적 `status == "disconnected"` check다(retried run은
delete_credential의 zero-row no-op에 의존하고 version을 계속 bump하는 대신, credential/version을
건드리기 전에 멈춘다).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.mail_sources import repository


async def purge_source(connection: AsyncConnection, *, source_id: uuid.UUID) -> None:
    account = await repository.get_connected_account(connection, connected_account_id=source_id)
    if account is None or account["status"] == "disconnected":
        return
    await repository.delete_credential(connection, connected_account_id=source_id)
    await repository.mark_account_status(
        connection,
        account_id=source_id,
        status="disconnected",
        version=account["version"] + 1,
    )
