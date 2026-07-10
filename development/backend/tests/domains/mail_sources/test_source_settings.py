import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select

from app.core.database import engine
from app.core.outbox import outbox_events
from app.domains.identity.models import workspaces
from app.domains.mail_sources.schemas import ConnectGmailSourceInput
from app.domains.mail_sources.service import connect_gmail_source, update_gmail_source_settings


async def _seed_workspace() -> uuid.UUID:
    workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    return workspace_id


async def _seed_source(**overrides) -> tuple:
    data = {
        "workspace_id": await _seed_workspace(),
        "gmail_address": f"user-{uuid.uuid4()}@gmail.com",
        "access_token": "ya29.a0-example-access-token",
        "refresh_token": "1//0g-example-refresh-token",
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    data.update(overrides)
    async with engine.begin() as connection:
        source, _ = await connect_gmail_source(connection, ConnectGmailSourceInput(**data))
    return source, data["gmail_address"]


async def test_display_name_falls_back_to_gmail_address_when_unset() -> None:
    source, gmail_address = await _seed_source()

    async with engine.begin() as connection:
        result = await update_gmail_source_settings(
            connection, connected_account_id=source.id, changes={}
        )

    assert result.display_name is None
    assert result.effective_display_name == gmail_address


async def test_toggle_updates_and_emits_settings_changed_event() -> None:
    source, _ = await _seed_source()

    async with engine.begin() as connection:
        result = await update_gmail_source_settings(
            connection,
            connected_account_id=source.id,
            changes={"summary_enabled": False, "display_name": "My Work Inbox"},
        )

    assert result.summary_enabled is False
    assert result.briefing_enabled is True
    assert result.display_name == "My Work Inbox"
    assert result.effective_display_name == "My Work Inbox"

    key = f"source:{source.id}:settings:1"
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.idempotency_key == key)
            )
        ).mappings().first()
    assert row is not None
    assert row["event_type"] == "gmail_source_settings_changed"


async def test_noop_update_does_not_emit_event() -> None:
    source, _ = await _seed_source()

    async with engine.begin() as connection:
        first = await update_gmail_source_settings(
            connection, connected_account_id=source.id, changes={"summary_enabled": False}
        )
    async with engine.begin() as connection:
        second = await update_gmail_source_settings(
            connection, connected_account_id=source.id, changes={"summary_enabled": False}
        )

    assert first.summary_enabled is False
    assert second.summary_enabled is False

    key = f"source:{source.id}:settings:1"
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(outbox_events).where(
                    outbox_events.c.event_type == "gmail_source_settings_changed",
                    outbox_events.c.idempotency_key == key,
                )
            )
        ).all()
    assert len(rows) == 1


async def test_pause_transitions_status_and_unpause_reverts_it() -> None:
    source, _ = await _seed_source()

    async with engine.begin() as connection:
        paused_result = await update_gmail_source_settings(
            connection, connected_account_id=source.id, changes={"paused": True}
        )
    assert paused_result.status == "paused"
    assert paused_result.paused is True

    async with engine.begin() as connection:
        resumed_result = await update_gmail_source_settings(
            connection, connected_account_id=source.id, changes={"paused": False}
        )
    assert resumed_result.status == "connected"
    assert resumed_result.paused is False


async def test_briefing_and_notification_toggles_independent() -> None:
    source, _ = await _seed_source()

    async with engine.begin() as connection:
        result = await update_gmail_source_settings(
            connection,
            connected_account_id=source.id,
            changes={"briefing_enabled": False, "notification_enabled": False},
        )

    assert result.briefing_enabled is False
    assert result.notification_enabled is False
    assert result.summary_enabled is True


async def test_get_settings_returns_current_values_without_mutation() -> None:
    """[읽기] GET용 서비스 — 현재 설정을 그대로 반환하고 version·outbox를 건드리지 않는다."""
    from app.domains.mail_sources.service import get_gmail_source_settings

    source, gmail_address = await _seed_source()

    async with engine.begin() as connection:
        await update_gmail_source_settings(
            connection, connected_account_id=source.id, changes={"summary_enabled": False}
        )
    async with engine.connect() as connection:
        result = await get_gmail_source_settings(connection, connected_account_id=source.id)
        events = (
            await connection.execute(
                select(outbox_events).where(outbox_events.c.event_type == "gmail_source_settings_changed")
            )
        ).mappings().all()

    assert result.connected_account_id == source.id
    assert result.gmail_address == gmail_address
    assert result.summary_enabled is False
    assert result.briefing_enabled is True
    # 읽기 전에 발생한 변경 1건 외에 추가 이벤트 없음(읽기는 무부작용).
    matching = [e for e in events if e["payload"].get("source_id") == str(source.id)]
    assert len(matching) == 1
