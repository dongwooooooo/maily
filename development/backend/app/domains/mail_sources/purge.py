"""PURGE_HANDLER(source_id) — _integration-contract.md §4, Task 13.

Runs last in the orchestration job's call order — every other domain's
message-scoped content is gone by this point (mail_intake's purge_source
just ran, deleting gmail_messages itself), so this only needs to finish
mail_sources' own two disconnect-time-deferred steps: fully remove the
◆ content-bearing credential ciphertext (disconnect_gmail_source only
set revoked_at as a fast synchronous marker — this is the actual purge),
and flip the account to its terminal `disconnected` status.
`connected_gmail_accounts` itself is kept (not deleted) — module-
boundaries.md §8's "최소 audit 보존" (minimal audit retention).

[멱등] `connected_gmail_accounts` rows are never deleted, so `account is
None` only guards a nonexistent/already-hard-deleted source_id, not a
retried purge — the real idempotency guard is the explicit
`status == "disconnected"` check below (a retried run stops before
touching credential/version at all, instead of relying on
delete_credential's no-op-on-zero-rows and re-bumping version forever).
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
