"""mail_intake-owned outbox event.

module-boundaries.md Event Catalog: `gmail_snapshot_changed`,
`gmail_notification_received`, 그리고 jointly owned `gmail_source_recovery_needed`의
mail_intake 쪽. mail_intake는 이를 append하고 다른 domain을 직접 호출하지 않는다. consumer는
outbox dispatcher를 통해 이를 집는다(이 task 범위 밖, _integration-contract.md §3 참고).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.outbox import append_event


async def publish_snapshot_changed(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    workspace_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    message_ids: list[uuid.UUID],
) -> None:
    """message_ids가 빈 sync_run은 publish하지 않는다.

    빈 event는 모든 consumer를 불필요하게 깨울 뿐이다(mail_intake.md
    "메시지_ids가 빈 sync_run은 event를 발행하지 않는다").

    consumer(build_briefing, IC2/IC3)가 자체 cross-domain lookup 없이 write scope를 잡을 수
    있도록 `workspace_id`를 포함한다. caller는 sync 실행을 위해 load한 account row에서 이미
    이 값을 갖고 있으므로 여기서 추가 query는 없다.
    """
    if not message_ids:
        return
    await append_event(
        connection,
        event_type="gmail_snapshot_changed",
        producer_domain="mail_intake",
        payload={
            "source_id": str(connected_account_id),
            "workspace_id": str(workspace_id),
            "sync_run_id": str(sync_run_id),
            "message_ids": [str(message_id) for message_id in message_ids],
        },
        idempotency_key=f"source:{connected_account_id}:snapshot:{sync_run_id}",
    )


async def publish_notification_received(
    connection: AsyncConnection, *, email_address: str, history_id: int
) -> None:
    await append_event(
        connection,
        event_type="gmail_notification_received",
        producer_domain="mail_intake",
        payload={"email_address": email_address, "history_id": history_id},
        idempotency_key=f"gmail-notification:{email_address}:{history_id}",
    )


async def publish_recovery_needed(
    connection: AsyncConnection,
    *,
    connected_account_id: uuid.UUID,
    workspace_id: uuid.UUID,
    reason: str,
    version: int,
) -> None:
    """mail_intake.md 기준 `reason`은 {"auth_error", "scope_reduced", "watch_failed"}.

    `version`은 caller가 이미 load한 connected_gmail_accounts.version이다(mail_sources가 이
    counter를 소유). 같은 account version에서 반복되는 failure가 다시 notify하지 않도록
    idempotency disambiguator로 사용한다. `workspace_id`/`version`은 idempotency_key에만 쓰는
    것이 아니라 payload에도 모두 포함한다. IC7의 notifications.resolve_route_target이 둘 다
    필요로 한다.
    """
    await append_event(
        connection,
        event_type="gmail_source_recovery_needed",
        producer_domain="mail_intake",
        payload={
            "source_id": str(connected_account_id),
            "workspace_id": str(workspace_id),
            "reason": reason,
            "version": version,
        },
        idempotency_key=f"source:{connected_account_id}:recovery:{reason}:{version}",
    )
