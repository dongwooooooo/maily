"""notifications service layer — docs/goals/backend-plans/notifications.md.

Task 12 file list 기준 두 책임이 여기 있다(별도 routing module 없음):

1. Route target mapping(`resolve_route_target`) — notifications.md "Route target 매핑"의
   고정 7-row table. pure function이며 I/O 없음.
2. `emit_notification` / `subscribe` / `list_notifications` — Command/Job 및 Read API
   behavior.

Trigger scope note: `app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS`(IC7)는 7개 mapped
trigger 중 4개(`gmail_source_recovery_needed`, `gmail_action_failed`,
`cleanup_proposal_created`, `reminder_reactivated`)를 outbox dispatcher에 wire한다.
mapping-table contract 자체가 아니라 dispatcher wiring만 scope down된 것이므로,
`resolve_route_target`은 `gmail_action_undone`과 두 `gmail_snapshot_changed` split을 포함한
7개 row를 모두 구현한다. `gmail_snapshot_changed` split 2개는 중요한 메일 vs daily briefing
split이 mail_intake의 실제 `gmail_snapshot_changed` payload에서 파생되지 않으므로 unwired로
둔다(payload 안에 importance signal 없음 — app/domains/mail_intake/events.py
`publish_snapshot_changed` 참고). `gmail_action_undone`은 자체 notification UX가 이번 범위가
아니라서 unwired로 둔다(briefing-rebuild 절반은 IC4의
`gmail_action_undone -> build_briefing`으로 이미 wired).

Payload contract note: `emit_notification(connection, trigger=..., payload=...)`는 raw
trigger + 해당 event의 raw payload를 받고 내부에서 notification_type/route_target을 resolve한다.
이는 _integration-contract.md §2의 literal already-resolved
`{notification_type, route_target, workspace_id}` shape가 아니라, notifications.md 자체 checklist
wording을 의도적으로 따른 것이다. `workspace_id`는 모든 trigger payload에 필요하다(아래 이
function 자체의 unconditional check). IC7-wired producer 4개는 이제 모두 이를 포함한다.
app/domains/mail_intake/events.py `publish_recovery_needed`,
app/domains/gmail_actions/jobs/execute_action.py의 `GMAIL_ACTION_FAILED` payload,
app/domains/assistant_decisions/cleanup.py의 `CLEANUP_PROPOSAL_CREATED` payload,
app/domains/briefing/jobs/reactivate_reminders.py의 `REMINDER_REACTIVATED` payload 참고.
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

# --- trigger identifier 정의 --------------------------------------------
# 아래 identifier 5개는 실제 outbox `event_type` value다(producing domain의 event.py constant를
# 정확히 mirror). `gmail_snapshot_changed:*` identifier 2개는 하나의 raw event type이 만들 수 있는
# 두 개의 distinct notification_type에 대한 이 domain 자체 qualifier다. module docstring
# "Trigger scope note" 참고.
TRIGGER_GMAIL_SOURCE_RECOVERY_NEEDED = "gmail_source_recovery_needed"
TRIGGER_GMAIL_ACTION_FAILED = "gmail_action_failed"
TRIGGER_GMAIL_ACTION_UNDONE = "gmail_action_undone"
TRIGGER_CLEANUP_PROPOSAL_CREATED = "cleanup_proposal_created"
TRIGGER_REMINDER_REACTIVATED = "reminder_reactivated"
TRIGGER_GMAIL_SNAPSHOT_CHANGED_IMPORTANT_MAIL = "gmail_snapshot_changed:important_mail"
TRIGGER_GMAIL_SNAPSHOT_CHANGED_DAILY_BRIEFING = "gmail_snapshot_changed:daily_briefing"

# --- screen(route_target["screen"]) 정의 --------------------------------
# 이 screen들에 대한 prior-art English slug는 docs/code 어디에도 없다(search로 확인 — docs는
# Korean prose로만 명명). coordinator open question: frontend wiring이 정확한 문자열에
# 의존하기 전에 confirm/rename해야 한다.
SCREEN_BRIEFING_TODAY = "briefing_today"
SCREEN_CLEANUP_REVIEW_QUEUE = "cleanup_review_queue"
SCREEN_ACCOUNT_SETTINGS = "account_settings"
SCREEN_ACTIVITY_LOG = "activity_log"

# --- notification_type values (notifications.md table 기준 고정) ---
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
        # defensive — notifications.md "[선행조건] route_target에 착지
        # 화면 키 없음 → 발행 거부(generic landing 방지)". resolve_route_target의 모든 branch는
        # fixed non-empty SCREEN_* constant를 넘기므로, 미래 edit가 이를 빠뜨릴 때만 실행된다.
        raise ValidationError(
            "route_target must include a screen — generic landing is not allowed"
        )
    return {"screen": screen, "item_id": str(item_id) if item_id is not None else None}


def resolve_route_target(trigger: str, payload: dict) -> RouteResolution | None:
    """notifications.md "Route target 매핑" table을 code로 표현한다.

    고정 7-row table에 없는 trigger는 None을 반환한다. generic-landing-prohibition invariant는
    unknown trigger가 notification을 만들지 않는다는 뜻이다(caller는 skip해야 함). fabricated
    landing screen은 절대 만들지 않는다. 이는 raise error가 아니라 의도적인 graceful no-op이다.
    이 function에 도달한 unknown/unwired trigger는 malformed payload가 아니라 이후 event에 대한
    upstream wiring question이다.
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
        # briefing의 실제 emitted payload(app/domains/briefing/jobs/reactivate_reminders.py)는
        # {reminder_id, briefing_item_state_id, message_id}다. briefing_item_id는 없다(그것은
        # ephemeral briefing_items.id이며 durable state의 key가 아님). version도 없다(reminders에는
        # version column이 없고, briefing 자체 reminder_reactivated_key가 version=0으로 고정).
        # reminder_id만으로도 reactivation별 unique하다(producer의 idempotency_key가 reminder row
        # id 기준). 따라서 여기서도 dedupe에 충분하다.
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

    caller의 transaction 안에서 실행된다(job handler가 이를 `engine.begin()`으로 감싼다). 따라서
    idempotency reservation, notification_events insert, outbox append가 함께 commit되거나
    rollback된다 — "[부분실패] event insert 성공·outbox append 실패 → 트랜잭션 롤백(한 트랜잭션)".
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
