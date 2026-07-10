import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import crypto
from app.core.errors import ConflictError, NotFoundError
from app.core.outbox import append_event
from app.domains.mail_sources import repository
from app.domains.mail_sources.schemas import (
    ConnectGmailSourceInput,
    ConnectedSource,
    DisconnectGmailSourceInput,
    DisconnectResult,
    SourceSettingsResult,
)


def _to_schema(row: dict) -> ConnectedSource:
    return ConnectedSource(
        id=row["id"],
        workspace_id=row["workspace_id"],
        gmail_address=row["gmail_address"],
        display_name=row["display_name"],
        status=row["status"],
        connected_at=row["connected_at"],
    )


async def connect_gmail_source(
    connection: AsyncConnection, data: ConnectGmailSourceInput
) -> tuple[ConnectedSource, bool]:
    """Gmail address를 workspace에 연결한다.

    active(disconnected가 아닌) connection 중 (workspace_id, gmail_address)에 대해 idempotent하다.
    sequential duplicate request는 아래 pre-check에 잡히고, 실제 concurrent request는 partial
    unique index에 잡힌 뒤 같은 re-query로 fallback한다. 어느 쪽이든 caller는 두 번째 row나 두
    번째 gmail_source_connected event 대신 기존 source와 is_new=False를 받는다.
    """
    existing = await repository.find_active_source_by_address(
        connection, workspace_id=data.workspace_id, gmail_address=data.gmail_address
    )
    if existing is not None:
        return _to_schema(existing), False

    account_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    try:
        async with connection.begin_nested():
            await repository.insert_connected_account(
                connection,
                account_id=account_id,
                workspace_id=data.workspace_id,
                gmail_address=data.gmail_address,
                status="connected",
                connected_at=now,
            )
    except IntegrityError:
        existing = await repository.find_active_source_by_address(
            connection, workspace_id=data.workspace_id, gmail_address=data.gmail_address
        )
        if existing is None:
            raise
        return _to_schema(existing), False

    await repository.insert_credential(
        connection,
        credential_id=uuid.uuid4(),
        connected_account_id=account_id,
        access_token_ciphertext=crypto.encrypt_token(data.access_token),
        refresh_token_ciphertext=crypto.encrypt_token(data.refresh_token),
        encryption_key_version=crypto.CURRENT_KEY_VERSION,
        scope=data.scope,
        expires_at=data.expires_at,
    )
    await repository.insert_default_settings(
        connection, settings_id=uuid.uuid4(), connected_account_id=account_id, updated_at=now
    )
    await append_event(
        connection,
        event_type="gmail_source_connected",
        producer_domain="mail_sources",
        payload={"source_id": str(account_id), "workspace_id": str(data.workspace_id)},
        idempotency_key=f"source:{account_id}:connected:0",
    )

    return (
        ConnectedSource(
            id=account_id,
            workspace_id=data.workspace_id,
            gmail_address=data.gmail_address,
            display_name=None,
            status="connected",
            connected_at=now,
        ),
        True,
    )


async def disconnect_gmail_source(
    connection: AsyncConnection, data: DisconnectGmailSourceInput
) -> DisconnectResult:
    """Task 13 / module-boundaries.md §8 "계정 연결 해제와 purge"의 synchronous half.

    source를 `disconnecting`으로 표시하고, credential을 revoke하며(revoked_at 설정 — local marker,
    이 POC에는 live Gmail revoke call 없음), `gmail_source_disconnected`를 emit한다. 그러면 async
    purge orchestration(mail_sources.jobs.purge_disconnected_source, IC8)이 각 domain의
    PURGE_HANDLER를 실행할 수 있다.

    [멱등] already-disconnecting/disconnected는 error가 아니라 no-op이다. retry된 disconnect
    request는 두 번째 event를 emit하거나 version을 다시 bump하면 안 된다.
    """
    account = await repository.get_connected_account(
        connection, connected_account_id=data.connected_account_id
    )
    if account is None or account["workspace_id"] != data.workspace_id:
        raise NotFoundError("gmail source not found")
    if account["status"] in ("disconnecting", "disconnected"):
        return DisconnectResult(connected_account_id=data.connected_account_id, status=account["status"])

    now = datetime.now(timezone.utc)
    new_version = account["version"] + 1
    await repository.mark_account_status(
        connection,
        account_id=data.connected_account_id,
        status="disconnecting",
        version=new_version,
        disconnected_at=now,
    )
    await repository.revoke_credential(
        connection, connected_account_id=data.connected_account_id, revoked_at=now
    )
    await append_event(
        connection,
        event_type="gmail_source_disconnected",
        producer_domain="mail_sources",
        payload={"source_id": str(data.connected_account_id), "workspace_id": str(data.workspace_id)},
        idempotency_key=f"source:{data.connected_account_id}:disconnected:{new_version}",
    )
    return DisconnectResult(connected_account_id=data.connected_account_id, status="disconnecting")


def _to_settings_result(account: dict, settings_row: dict) -> SourceSettingsResult:
    return SourceSettingsResult(
        connected_account_id=account["id"],
        gmail_address=account["gmail_address"],
        display_name=account["display_name"],
        effective_display_name=account["display_name"] or account["gmail_address"],
        status=account["status"],
        briefing_enabled=settings_row["briefing_enabled"],
        summary_enabled=settings_row["summary_enabled"],
        notification_enabled=settings_row["notification_enabled"],
        paused=settings_row["paused"],
    )


async def update_gmail_source_settings(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID, changes: dict
) -> SourceSettingsResult:
    """부분 settings/display_name/pause update를 적용한다.

    `changes`는 caller가 실제 제공한 field만 담는다(예: PATCH body의 exclude_unset dict).
    없는 field는 current value를 유지한다. paused=true는 status를 "paused"로 transition하고,
    현재 paused 상태에서 paused=false면 "connected"로 되돌린다(sync scheduler가 그 이후 상태를
    전진시키며, 이 domain은 실제 sync state를 재평가하지 않음). no-op update(merged value가
    current value와 같음)는 version bump와 outbox event를 완전히 건너뛴다.
    """
    account = await repository.get_connected_account(
        connection, connected_account_id=connected_account_id
    )
    if account is None:
        raise NotFoundError("gmail source not found")
    if account["status"] in ("disconnecting", "disconnected"):
        raise ConflictError("gmail source is disconnecting or disconnected")

    settings_row = await repository.get_source_settings(
        connection, connected_account_id=connected_account_id
    )

    merged_display_name = changes.get("display_name", account["display_name"])
    merged_briefing = changes.get("briefing_enabled", settings_row["briefing_enabled"])
    merged_summary = changes.get("summary_enabled", settings_row["summary_enabled"])
    merged_notification = changes.get(
        "notification_enabled", settings_row["notification_enabled"]
    )
    merged_paused = changes.get("paused", settings_row["paused"])

    changed = (
        merged_display_name != account["display_name"]
        or merged_briefing != settings_row["briefing_enabled"]
        or merged_summary != settings_row["summary_enabled"]
        or merged_notification != settings_row["notification_enabled"]
        or merged_paused != settings_row["paused"]
    )
    if not changed:
        return _to_settings_result(account, settings_row)

    new_status = account["status"]
    if merged_paused and not settings_row["paused"]:
        new_status = "paused"
    elif not merged_paused and settings_row["paused"] and account["status"] == "paused":
        new_status = "connected"

    now = datetime.now(timezone.utc)
    new_version = account["version"] + 1

    await repository.update_connected_account(
        connection,
        account_id=connected_account_id,
        display_name=merged_display_name,
        status=new_status,
        version=new_version,
    )
    await repository.update_source_settings(
        connection,
        connected_account_id=connected_account_id,
        briefing_enabled=merged_briefing,
        summary_enabled=merged_summary,
        notification_enabled=merged_notification,
        paused=merged_paused,
        updated_at=now,
    )
    await append_event(
        connection,
        event_type="gmail_source_settings_changed",
        producer_domain="mail_sources",
        payload={"source_id": str(connected_account_id)},
        idempotency_key=f"source:{connected_account_id}:settings:{new_version}",
    )

    account = {**account, "display_name": merged_display_name, "status": new_status}
    settings_row = {
        **settings_row,
        "briefing_enabled": merged_briefing,
        "summary_enabled": merged_summary,
        "notification_enabled": merged_notification,
        "paused": merged_paused,
    }
    return _to_settings_result(account, settings_row)
