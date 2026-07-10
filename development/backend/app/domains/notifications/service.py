"""notifications service layer — docs/goals/backend-plans/notifications.md.

Two responsibilities live here per the Task 12 file list (no separate
routing module):

1. Route target mapping (`resolve_route_target`) — the fixed 7-row table
   from notifications.md "Route target 매핑". Pure function, no I/O.
2. `emit_notification` / `subscribe` / `list_notifications` — the
   Command/Job and Read API behaviors.

Trigger scope note: `app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS` (IC7)
wires 4 of the 7 mapped triggers to the outbox dispatcher —
`gmail_source_recovery_needed`, `gmail_action_failed`,
`cleanup_proposal_created`, `reminder_reactivated`. `resolve_route_target`
still implements all 7 rows — including `gmail_action_undone` and the two
`gmail_snapshot_changed` splits — because the mapping-table contract
itself isn't scoped down, only the dispatcher wiring is. The 2
`gmail_snapshot_changed` splits stay unwired because the split (important
mail vs. daily briefing) isn't derivable from mail_intake's actual
`gmail_snapshot_changed` payload (no importance signal in it — see
app/domains/mail_intake/events.py `publish_snapshot_changed`).
`gmail_action_undone` stays unwired because its own notification UX
wasn't scoped for this round (its briefing-rebuild half is already wired
via IC4's `gmail_action_undone -> build_briefing`).

Payload contract note: `emit_notification(connection, trigger=...,
payload=...)` takes the raw trigger + that event's raw payload and
resolves notification_type/route_target internally — deliberately not
_integration-contract.md §2's literal already-resolved
`{notification_type, route_target, workspace_id}` shape, following
notifications.md's own checklist wording instead. `workspace_id` is
required on every trigger's payload (this function's own unconditional
check below); all 4 IC7-wired producers now include it — see
app/domains/mail_intake/events.py `publish_recovery_needed`,
app/domains/gmail_actions/jobs/execute_action.py's `GMAIL_ACTION_FAILED`
payload, app/domains/assistant_decisions/cleanup.py's
`CLEANUP_PROPOSAL_CREATED` payload, and
app/domains/briefing/jobs/reactivate_reminders.py's
`REMINDER_REACTIVATED` payload.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import idempotency
from app.core.errors import ValidationError
from app.domains.notifications import repository
from app.domains.notifications.events import record_notification_event_created
from app.domains.notifications.schemas import (
    NotificationEvent,
    NotificationSubscription,
    RouteTarget,
    SubscribeInput,
)

logger = structlog.get_logger()

# --- trigger identifiers -----------------------------------------------
# The 5 identifiers below are real outbox `event_type` values (mirroring
# the producing domains' own event.py constants exactly). The two
# `gmail_snapshot_changed:*` identifiers are this domain's own qualifier
# for the two distinct notification_types that one raw event type can
# produce — see module docstring "Trigger scope note".
TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED = "gmail_source_recovery_needed"
TRIGGER_GMAIL_ACTION_FAILED = "gmail_action_failed"
TRIGGER_GMAIL_ACTION_UNDONE = "gmail_action_undone"
TRIGGER_CLEANUP_PROPOSAL_CREATED = "cleanup_proposal_created"
TRIGGER_REMINDER_REACTIVATED = "reminder_reactivated"
TRIGGER_GMAIL_SNAPSHOT_CHANGED_IMPORTANT_MAIL = "gmail_snapshot_changed:important_mail"
TRIGGER_GMAIL_SNAPSHOT_CHANGED_DAILY_BRIEFING = "gmail_snapshot_changed:daily_briefing"

# --- screens (route_target["screen"]) -----------------------------------
# No prior-art English slug exists anywhere in docs/code for these
# screens (confirmed by search — docs only name them in Korean prose).
# Open question for coordinator: confirm/rename these before frontend
# wiring depends on the exact strings.
SCREEN_BRIEFING_TODAY = "briefing_today"
SCREEN_CLEANUP_REVIEW_QUEUE = "cleanup_review_queue"
SCREEN_ACCOUNT_SETTINGS = "account_settings"
SCREEN_ACTIVITY_LOG = "activity_log"

# --- notification_type values (fixed, from notifications.md's table) ---
NOTIFICATION_TYPE_IMPORTANT_MAIL = "important_mail"
NOTIFICATION_TYPE_REMINDER_DUE = "reminder_due"
NOTIFICATION_TYPE_DAILY_BRIEFING = "daily_briefing"
NOTIFICATION_TYPE_CLEANUP_REVIEW = "cleanup_review"
NOTIFICATION_TYPE_RECOVERY_NEEDED = "recovery_needed"
NOTIFICATION_TYPE_ACTION_FAILED = "action_failed"
NOTIFICATION_TYPE_ACTION_UNDONE = "action_undone"

_EMIT_IDEMPOTENCY_SCOPE = "notifications.emit_notification"
_EMIT_IDEMPOTENCY_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class RouteResolution:
    notification_type: str
    route_target: dict
    dedupe_key: str
    connected_account_id: uuid.UUID | None


def _require(payload: dict, field: str):
    value = payload.get(field)
    if value is None or value == "":
        raise ValidationError(f"{field} is required in event payload")
    return value


def _uuid(payload: dict, field: str) -> uuid.UUID:
    return uuid.UUID(str(_require(payload, field)))


def _optional_uuid(payload: dict, field: str) -> uuid.UUID | None:
    value = payload.get(field)
    return uuid.UUID(str(value)) if value else None


def _route_target(screen: str, item_id: uuid.UUID | None) -> dict:
    if not screen:
        # Defensive — notifications.md "[선행조건] route_target에 착지
        # 화면 키 없음 → 발행 거부(generic landing 방지)". Every branch
        # in resolve_route_target passes a fixed non-empty SCREEN_*
        # constant, so this only fires if a future edit forgets one.
        raise ValidationError(
            "route_target must include a screen — generic landing is not allowed"
        )
    return {"screen": screen, "item_id": str(item_id) if item_id is not None else None}


def resolve_route_target(trigger: str, payload: dict) -> RouteResolution | None:
    """notifications.md "Route target 매핑" table, as code.

    Returns None for any trigger not in the fixed 7-row table — the
    generic-landing-prohibition invariant means an unrecognized trigger
    produces NO notification (caller must skip), never a fabricated
    landing screen. This is intentionally a graceful no-op, not a raised
    error — an unknown/unwired trigger reaching this function is an
    upstream wiring question for a later event, not a malformed payload.
    """
    if trigger == TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED:
        source_id = _uuid(payload, "source_id")
        reason = _require(payload, "reason")
        version = _require(payload, "version")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_RECOVERY_NEEDED,
            route_target=_route_target(SCREEN_ACCOUNT_SETTINGS, source_id),
            dedupe_key=f"source:{source_id}:recovery:{reason}:{version}",
            connected_account_id=source_id,
        )

    if trigger == TRIGGER_GMAIL_ACTION_FAILED:
        command_id = _uuid(payload, "command_id")
        version = _require(payload, "version")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_ACTION_FAILED,
            route_target=_route_target(SCREEN_ACTIVITY_LOG, command_id),
            dedupe_key=f"command:{command_id}:failed:{version}",
            connected_account_id=_optional_uuid(payload, "connected_account_id"),
        )

    if trigger == TRIGGER_GMAIL_ACTION_UNDONE:
        command_id = _uuid(payload, "command_id")
        version = _require(payload, "version")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_ACTION_UNDONE,
            route_target=_route_target(SCREEN_ACTIVITY_LOG, command_id),
            dedupe_key=f"command:{command_id}:undone:{version}",
            connected_account_id=_optional_uuid(payload, "connected_account_id"),
        )

    if trigger == TRIGGER_CLEANUP_PROPOSAL_CREATED:
        proposal_id = _uuid(payload, "proposal_id")
        message_id = _require(payload, "message_id")
        proposal_version = _require(payload, "proposal_version")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_CLEANUP_REVIEW,
            route_target=_route_target(SCREEN_CLEANUP_REVIEW_QUEUE, proposal_id),
            dedupe_key=f"message:{message_id}:cleanup:{proposal_version}",
            connected_account_id=None,
        )

    if trigger == TRIGGER_REMINDER_REACTIVATED:
        # briefing's actual emitted payload (app/domains/briefing/jobs/
        # reactivate_reminders.py) is {reminder_id, briefing_item_state_id,
        # message_id} — no briefing_item_id (that's the ephemeral
        # briefing_items.id, not what briefing keys durable state by), and
        # no version (reminders have no version column; briefing's own
        # reminder_reactivated_key fixes version=0). reminder_id alone is
        # unique per reactivation (producer's idempotency_key is keyed on
        # the reminder row id), so it's sufficient for dedupe here too.
        reminder_id = _require(payload, "reminder_id")
        message_id = _uuid(payload, "message_id")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_REMINDER_DUE,
            route_target=_route_target(SCREEN_BRIEFING_TODAY, message_id),
            dedupe_key=f"reminder:{reminder_id}:reactivated",
            connected_account_id=None,
        )

    if trigger == TRIGGER_GMAIL_SNAPSHOT_CHANGED_IMPORTANT_MAIL:
        source_id = _uuid(payload, "source_id")
        message_id = _uuid(payload, "message_id")
        sync_run_id = _require(payload, "sync_run_id")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_IMPORTANT_MAIL,
            route_target=_route_target(SCREEN_BRIEFING_TODAY, message_id),
            dedupe_key=f"source:{source_id}:snapshot:{sync_run_id}:important:{message_id}",
            connected_account_id=source_id,
        )

    if trigger == TRIGGER_GMAIL_SNAPSHOT_CHANGED_DAILY_BRIEFING:
        source_id = _uuid(payload, "source_id")
        sync_run_id = _require(payload, "sync_run_id")
        return RouteResolution(
            notification_type=NOTIFICATION_TYPE_DAILY_BRIEFING,
            route_target=_route_target(SCREEN_BRIEFING_TODAY, None),
            dedupe_key=f"source:{source_id}:snapshot:{sync_run_id}:daily",
            connected_account_id=source_id,
        )

    return None


async def emit_notification(
    connection: AsyncConnection, *, trigger: str, payload: dict
) -> uuid.UUID | None:
    """Command/Job `emit_notification` — notifications.md "Command/Job:
    emit_notification" 체크리스트 [정상]/[멱등]/[동시]/[선행조건]/[부분실패].

    Runs inside the caller's transaction (job handler wraps this in
    `engine.begin()`) so the idempotency reservation, notification_events
    insert, and outbox append commit or roll back together — "[부분실패]
    event insert 성공·outbox append 실패 → 트랜잭션 롤백(한 트랜잭션)".
    """
    resolution = resolve_route_target(trigger, payload)
    if resolution is None:
        logger.info(
            "매핑되지 않은 트리거라 알림 생성 건너뜀 — generic landing 생성 안 함",
            trigger=trigger,
        )
        return None

    workspace_id = _uuid(payload, "workspace_id")

    is_new_key = await idempotency.reserve(
        connection,
        scope=_EMIT_IDEMPOTENCY_SCOPE,
        key=resolution.dedupe_key,
        expires_at=datetime.now(timezone.utc) + _EMIT_IDEMPOTENCY_TTL,
    )
    if not is_new_key:
        cached = await idempotency.get_response(
            connection, scope=_EMIT_IDEMPOTENCY_SCOPE, key=resolution.dedupe_key
        )
        cached_id = cached.get("notification_id") if cached else None
        logger.info(
            "같은 원인으로 이미 처리된 알림 — 재실행 무시",
            trigger=trigger,
            dedupe_key=resolution.dedupe_key,
        )
        return uuid.UUID(cached_id) if cached_id else None

    if resolution.connected_account_id is not None:
        enabled = await repository.get_source_notification_enabled(
            connection, connected_account_id=resolution.connected_account_id
        )
        if not enabled:
            await idempotency.store_response(
                connection,
                scope=_EMIT_IDEMPOTENCY_SCOPE,
                key=resolution.dedupe_key,
                response_snapshot={"notification_id": None},
            )
            logger.info(
                "계정 알림 설정 비활성화로 알림 생성 건너뜀",
                connected_account_id=str(resolution.connected_account_id),
                notification_type=resolution.notification_type,
            )
            return None

    notification_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    await repository.insert_notification_event(
        connection,
        notification_id=notification_id,
        workspace_id=workspace_id,
        notification_type=resolution.notification_type,
        route_target=resolution.route_target,
        created_at=now,
    )
    await record_notification_event_created(
        connection,
        notification_id=notification_id,
        workspace_id=workspace_id,
        notification_type=resolution.notification_type,
        route_target=resolution.route_target,
    )
    await idempotency.store_response(
        connection,
        scope=_EMIT_IDEMPOTENCY_SCOPE,
        key=resolution.dedupe_key,
        response_snapshot={"notification_id": str(notification_id)},
    )
    logger.info(
        "알림 이벤트 생성",
        notification_id=str(notification_id),
        notification_type=resolution.notification_type,
    )
    return notification_id


async def subscribe(connection: AsyncConnection, data: SubscribeInput) -> NotificationSubscription:
    """browser push 구독 등록/갱신 — notifications.md "동작: browser push
    구독" 체크리스트."""
    endpoint = data.endpoint.strip()
    if not endpoint:
        raise ValidationError("endpoint must not be blank")
    if not data.keys:
        raise ValidationError("keys must not be empty")

    effective_id = await repository.upsert_subscription(
        connection,
        subscription_id=uuid.uuid4(),
        user_id=data.user_id,
        endpoint=endpoint,
        keys=data.keys,
    )
    row = await repository.get_subscription(connection, subscription_id=effective_id)
    logger.info("브라우저 푸시 구독 등록", subscription_id=str(effective_id))
    return NotificationSubscription(
        id=row["id"],
        user_id=row["user_id"],
        endpoint=row["endpoint"],
        revoked_at=row["revoked_at"],
    )


async def list_notifications(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[NotificationEvent]:
    rows = await repository.list_notification_events(connection, workspace_id=workspace_id)
    return [
        NotificationEvent(
            id=row["id"],
            workspace_id=row["workspace_id"],
            notification_type=row["notification_type"],
            route_target=RouteTarget(**row["route_target"]),
            read_at=row["read_at"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
