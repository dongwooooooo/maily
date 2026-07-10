
from sqlalchemy import select

from app.core.database import engine
from app.domains.mail_sources.models import connected_gmail_accounts
from app.domains.notifications import service
from app.domains.notifications.jobs.emit_notification import run_emit_notification
from app.domains.notifications.models import notification_events
from tests.domains.notifications.conftest import seed_scope


async def _emit_recovery(*, workspace_id, source_id, reason: str, version: int):
    async with engine.begin() as connection:
        return await run_emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_id),
                "source_id": str(source_id),
                "reason": reason,
                "version": version,
            },
        )


async def test_recovery_event_routes_to_account_settings() -> None:
    """[정상] gmail_source_recovery_needed(reason=token_refresh_failed/
    scope_reduced/auth_error) 수신 -> recovery_needed 알림, route_target=
    계정 설정 + 해당 source_id."""
    workspace_id, _user_id, account_id = await seed_scope()

    for reason in ("token_refresh_failed", "scope_reduced", "auth_error"):
        notification_id = await _emit_recovery(
            workspace_id=workspace_id, source_id=account_id, reason=reason, version=0
        )
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    select(notification_events).where(notification_events.c.id == notification_id)
                )
            ).mappings().first()
        assert row["notification_type"] == service.NOTIFICATION_TYPE_RECOVERY_NEEDED
        assert row["route_target"]["screen"] == service.SCREEN_ACCOUNT_SETTINGS
        assert row["route_target"]["item_id"] == str(account_id)
        # version=0에서 각 reason은 dedupe-distinct라 loop 동안 별도 row 3개가 쌓인다.
        # 아래 count assertion으로 확인한다.

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
    assert len(rows) == 3  # distinct reason마다 하나


async def test_recovery_idempotent_per_reason() -> None:
    """[멱등] 같은 source에 대한 recovery event 반복 도착(같은 reason+version)
    -> 알림 1건. reason이 바뀌면 별개 알림."""
    workspace_id, _user_id, account_id = await seed_scope()

    first_id = await _emit_recovery(
        workspace_id=workspace_id, source_id=account_id, reason="auth_error", version=1
    )
    repeat_id = await _emit_recovery(
        workspace_id=workspace_id, source_id=account_id, reason="auth_error", version=1
    )
    other_reason_id = await _emit_recovery(
        workspace_id=workspace_id, source_id=account_id, reason="scope_reduced", version=1
    )

    assert first_id == repeat_id
    assert first_id != other_reason_id

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
    assert len(rows) == 2


async def test_recovery_does_not_mutate_source_state() -> None:
    """[데이터경계] notifications는 connected_gmail_accounts.status를 읽거나
    쓰지 않는다 — recovery 알림 발행이 source state를 바꾸지 않는다
    (view-only 경계)."""
    workspace_id, _user_id, account_id = await seed_scope()
    async with engine.begin() as connection:
        await connection.execute(
            connected_gmail_accounts.update()
            .where(connected_gmail_accounts.c.id == account_id)
            .values(status="permission_needed")
        )

    await _emit_recovery(workspace_id=workspace_id, source_id=account_id, reason="auth_error", version=0)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(connected_gmail_accounts.c.status).where(
                    connected_gmail_accounts.c.id == account_id
                )
            )
        ).first()
    assert row[0] == "permission_needed"  # notifications가 바꾸지 않음
