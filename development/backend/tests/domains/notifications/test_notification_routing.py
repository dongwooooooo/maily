import uuid

import pytest
from sqlalchemy import select

from app.core.database import engine
from app.core.errors import ValidationError
from app.domains.notifications import repository, service
from app.domains.notifications.models import notification_events
from app.domains.notifications.schemas import SubscribeInput
from tests.domains.notifications.conftest import (
    seed_scope,
    seed_user,
    seed_workspace,
)


# --- Route target mapping 검증(notifications.md "Route target 매핑") -----


async def test_type_maps_to_screen_and_item() -> None:
    """notifications.md의 7-row mapping table의 모든 row는 고정된
    (notification_type, screen, item_id) triple로 resolve된다. 어떤 event kind도
    자체 screen을 만들지 않는다."""
    source_id = uuid.uuid4()
    command_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    message_id = uuid.uuid4()
    reminder_message_id = uuid.uuid4()

    cases = [
        (
            service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            {"workspace_id": str(uuid.uuid4()), "source_id": str(source_id), "reason": "auth_error", "version": 0},
            service.NOTIFICATION_TYPE_RECOVERY_NEEDED,
            service.SCREEN_ACCOUNT_SETTINGS,
            source_id,
        ),
        (
            service.TRIGGER_GMAIL_ACTION_FAILED,
            {"workspace_id": str(uuid.uuid4()), "command_id": str(command_id), "version": 1},
            service.NOTIFICATION_TYPE_ACTION_FAILED,
            service.SCREEN_ACTIVITY_LOG,
            command_id,
        ),
        (
            service.TRIGGER_GMAIL_ACTION_UNDONE,
            {"workspace_id": str(uuid.uuid4()), "command_id": str(command_id), "version": 2},
            service.NOTIFICATION_TYPE_ACTION_UNDONE,
            service.SCREEN_ACTIVITY_LOG,
            command_id,
        ),
        (
            service.TRIGGER_CLEANUP_PROPOSAL_CREATED,
            {
                "workspace_id": str(uuid.uuid4()),
                "proposal_id": str(proposal_id),
                "message_id": str(message_id),
                "proposal_version": 0,
            },
            service.NOTIFICATION_TYPE_CLEANUP_REVIEW,
            service.SCREEN_CLEANUP_REVIEW_QUEUE,
            proposal_id,
        ),
        (
            service.TRIGGER_REMINDER_REACTIVATED,
            {
                "workspace_id": str(uuid.uuid4()),
                "reminder_id": str(uuid.uuid4()),
                "briefing_item_state_id": str(uuid.uuid4()),
                "message_id": str(reminder_message_id),
            },
            service.NOTIFICATION_TYPE_REMINDER_DUE,
            service.SCREEN_BRIEFING_TODAY,
            reminder_message_id,
        ),
        (
            service.TRIGGER_GMAIL_SNAPSHOT_CHANGED_IMPORTANT_MAIL,
            {
                "workspace_id": str(uuid.uuid4()),
                "source_id": str(source_id),
                "message_id": str(message_id),
                "sync_run_id": str(uuid.uuid4()),
            },
            service.NOTIFICATION_TYPE_IMPORTANT_MAIL,
            service.SCREEN_BRIEFING_TODAY,
            message_id,
        ),
        (
            service.TRIGGER_GMAIL_SNAPSHOT_CHANGED_DAILY_BRIEFING,
            {"workspace_id": str(uuid.uuid4()), "source_id": str(source_id), "sync_run_id": str(uuid.uuid4())},
            service.NOTIFICATION_TYPE_DAILY_BRIEFING,
            service.SCREEN_BRIEFING_TODAY,
            None,
        ),
    ]

    for trigger, payload, expected_type, expected_screen, expected_item_id in cases:
        resolution = service.resolve_route_target(trigger, payload)
        assert resolution is not None, trigger
        assert resolution.notification_type == expected_type
        assert resolution.route_target["screen"] == expected_screen
        expected_item = str(expected_item_id) if expected_item_id is not None else None
        assert resolution.route_target["item_id"] == expected_item


def test_daily_briefing_has_no_selected_item_but_keeps_screen() -> None:
    """[매핑 규칙] selected item 부재는 허용, 화면 부재는 불가."""
    resolution = service.resolve_route_target(
        service.TRIGGER_GMAIL_SNAPSHOT_CHANGED_DAILY_BRIEFING,
        {"workspace_id": str(uuid.uuid4()), "source_id": str(uuid.uuid4()), "sync_run_id": str(uuid.uuid4())},
    )
    assert resolution is not None
    assert resolution.route_target["screen"] == service.SCREEN_BRIEFING_TODAY
    assert resolution.route_target["item_id"] is None


# --- Generic landing 부정 case -------------------------------------------


def test_route_target_required_no_generic_landing_unmapped_trigger() -> None:
    """고정 mapping table에 없는 event kind는 route를 만들면 안 된다.
    resolve_route_target은 fabricated generic landing screen이 아니라 None(skip)으로
    degrade된다."""
    resolution = service.resolve_route_target("some_unmapped_event_type", {"workspace_id": str(uuid.uuid4())})
    assert resolution is None


def test_route_target_required_no_generic_landing_empty_screen_rejected() -> None:
    """Defensive guard: screen key 없는 route_target build는 즉시 reject된다.
    조용히 generic landing으로 바뀌면 안 된다."""
    with pytest.raises(ValidationError):
        service._route_target("", uuid.uuid4())


async def test_emit_notification_skips_silently_for_unmapped_trigger() -> None:
    """End-to-end: unmapped trigger는 notification_events row를 만들지 않고
    exception도 발생시키지 않는다(graceful skip이며 error나 generic landing이 아님)."""
    workspace_id = await seed_workspace()
    async with engine.begin() as connection:
        result = await service.emit_notification(
            connection, trigger="some_unmapped_event_type", payload={"workspace_id": str(workspace_id)}
        )
    assert result is None

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
    assert rows == []


# --- notification_enabled=false skip(account-related alert) 검증 ---------


async def test_notification_disabled_account_skipped() -> None:
    """[선행조건] 대상 계정 notification_enabled=false -> event 무시(row 없음)."""
    workspace_id, _user_id, account_id = await seed_scope(notification_enabled=False)

    async with engine.begin() as connection:
        result = await service.emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_id),
                "source_id": str(account_id),
                "reason": "auth_error",
                "version": 0,
            },
        )
    assert result is None

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(notification_events).where(notification_events.c.workspace_id == workspace_id)
            )
        ).mappings().all()
    assert rows == []


async def test_notification_enabled_account_not_skipped() -> None:
    """위 test의 control case다. notification_enabled=true(default)는 같은 trigger를 통과시킨다."""
    workspace_id, _user_id, account_id = await seed_scope(notification_enabled=True)

    async with engine.begin() as connection:
        result = await service.emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_id),
                "source_id": str(account_id),
                "reason": "auth_error",
                "version": 0,
            },
        )
    assert result is not None


# --- browser push subscription 검증 --------------------------------------


async def test_subscribe_registers_endpoint() -> None:
    user_id = await seed_user()
    endpoint = f"https://push.example.com/{uuid.uuid4()}"

    async with engine.begin() as connection:
        result = await service.subscribe(
            connection,
            SubscribeInput(user_id=user_id, endpoint=endpoint, keys={"p256dh": "key", "auth": "secret"}),
        )

    assert result.user_id == user_id
    assert result.endpoint == endpoint
    assert result.revoked_at is None
    assert not hasattr(result, "keys")


async def test_resubscribe_updates_not_duplicates() -> None:
    """[멱등] 같은 endpoint 재구독 -> 기존 row 갱신, 중복 row 안 생김."""
    user_id = await seed_user()
    endpoint = f"https://push.example.com/{uuid.uuid4()}"

    async with engine.begin() as connection:
        first = await service.subscribe(
            connection, SubscribeInput(user_id=user_id, endpoint=endpoint, keys={"p256dh": "key-1"})
        )
    async with engine.begin() as connection:
        second = await service.subscribe(
            connection, SubscribeInput(user_id=user_id, endpoint=endpoint, keys={"p256dh": "key-2"})
        )

    assert first.id == second.id

    async with engine.connect() as connection:
        row = await repository.get_subscription(connection, subscription_id=first.id)
    assert row["keys"] == {"p256dh": "key-2"}
    assert row["revoked_at"] is None


async def test_subscription_scoped_to_user() -> None:
    """[권한] 구독은 user 소유 — 다른 user의 구독과 섞이지 않는다."""
    user_a = await seed_user()
    user_b = await seed_user()
    endpoint_a = f"https://push.example.com/{uuid.uuid4()}"
    endpoint_b = f"https://push.example.com/{uuid.uuid4()}"

    async with engine.begin() as connection:
        sub_a = await service.subscribe(
            connection, SubscribeInput(user_id=user_a, endpoint=endpoint_a, keys={"p256dh": "a"})
        )
    async with engine.begin() as connection:
        sub_b = await service.subscribe(
            connection, SubscribeInput(user_id=user_b, endpoint=endpoint_b, keys={"p256dh": "b"})
        )

    async with engine.connect() as connection:
        row_a = await repository.get_subscription(connection, subscription_id=sub_a.id)
        row_b = await repository.get_subscription(connection, subscription_id=sub_b.id)

    assert row_a["user_id"] == user_a
    assert row_b["user_id"] == user_b
    assert row_a["id"] != row_b["id"]


# --- GET /notifications read model 검증 ----------------------------------


async def test_list_notifications_scoped() -> None:
    """[권한] 세션 workspace 스코프만 — 타 workspace 알림 안 섞임."""
    workspace_a, _, account_a = await seed_scope()
    workspace_b, _, account_b = await seed_scope()

    async with engine.begin() as connection:
        await service.emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_a),
                "source_id": str(account_a),
                "reason": "auth_error",
                "version": 0,
            },
        )
    async with engine.begin() as connection:
        await service.emit_notification(
            connection,
            trigger=service.TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED,
            payload={
                "workspace_id": str(workspace_b),
                "source_id": str(account_b),
                "reason": "auth_error",
                "version": 0,
            },
        )

    async with engine.connect() as connection:
        notifications_a = await service.list_notifications(connection, workspace_id=workspace_a)

    assert len(notifications_a) == 1
    assert notifications_a[0].workspace_id == workspace_a
    assert notifications_a[0].notification_type == service.NOTIFICATION_TYPE_RECOVERY_NEEDED


async def test_list_notifications_empty_is_not_an_error() -> None:
    """[빈상태] 알림 0건 -> 빈 배열(에러 아님)."""
    workspace_id = await seed_workspace()
    async with engine.connect() as connection:
        notifications = await service.list_notifications(connection, workspace_id=workspace_id)
    assert notifications == []
