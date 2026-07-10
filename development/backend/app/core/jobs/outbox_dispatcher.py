"""Outbox -> job_runs dispatcher — _integration-contract.md §3.

pending outbox_events를 읽고 각 event_type이 어떤 job_type을 queue해야 하는지
찾아 (event, job_type) pair마다 job_runs row 하나를 enqueue한 뒤 event를
dispatched로 표시한다. Producer domain은 consumer를 직접 호출하지 않는다. 이
module은 그 boundary를 넘는 유일한 곳이며, domain의 service/job 함수를 import하지
않고 범용으로 처리한다(event_type -> job_type 문자열 lookup).

Caller는 반드시 `app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS`(또는 더 좁은
subset)를 넘겨야 하며, `app.core.discovery.collect_event_consumers(...)`를 넘기면
안 된다. discovery map은 모든 domain의 *선언된* contract 의도이며, domain이 아직
실제로 wired되지 않았다고 명시한 entry도 포함한다. wiring module은 IC checkpoint별로
dispatch가 안전하다고 입증된 subset만 담는다. 이유는 wiring.py의 docstring 참고
(gmail_snapshot_changed의 message_ids list처럼 N-way fan-out이 필요한 event-type
payload shape는 이 generic한 1-event-to-1-job pass-through를 전혀 통과할 수 없다).
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.jobs.models import job_runs
from app.core.outbox import outbox_events


class MissingJobPayloadKeyError(Exception):
    """wired (event_type, job_type) pair가 job_type handler에 필요한 key가 빠진
    job_runs row를 enqueue하려 할 때 발생한다. 이는 data 문제가 아니라 wiring
    bug다(matching payload shape 없이 wiring.ACTIVE_EVENT_CONSUMERS entry가 추가된
    경우). worker가 집은 뒤에야 실패할 job을 조용히 queue하지 말고 dispatch 시점에
    명확히 실패해야 한다."""


# 현재 wiring.ACTIVE_EVENT_CONSUMERS를 통해 도달 가능한 job_type에 대한 최소
# required-key backstop. 새 IC entry를 추가할 때 함께 확장한다. full payload-shape
# validator가 아니라, IC1 review에서 발견된 정확한 failure mode를 막는 저렴한
# guard다. 즉 wired pair의 event payload가 job handler가 `payload["key"]`로 읽는
# key를 실제로 담지 않는 경우다.
_REQUIRED_PAYLOAD_KEYS: dict[str, set[str]] = {
    "register_watch": {"source_id"},
    "sync_full": {"source_id"},
    "build_briefing": {"workspace_id"},
    "generate_summary": {"message_id"},
    "classify_importance": {"message_id"},
    "execute_action": {"command_id"},
    "reconcile_action": {"message_id"},
    "purge_disconnected_source": {"source_id"},
}

# emit_notification의 job payload는 {"trigger": event_type, "payload": {...}} wrapper다.
# 따라서 top-level key를 보는 generic _REQUIRED_PAYLOAD_KEYS check로는 검증할 수
# 없다. 실제로 중요한 field는 한 단계 아래에 있으며, 어떤 field가 필요한지는 event를
# 만든 trigger에 따라 달라진다(notifications.service.resolve_route_target의 trigger별
# branch). workspace_id는 모든 trigger에 필요하고(emit_notification 자체의 무조건
# check), 나머지는 resolve_route_target과 정확히 맞춘다.
_EMIT_NOTIFICATION_REQUIRED_KEYS: dict[str, set[str]] = {
    "gmail_source_recovery_needed": {"workspace_id", "source_id", "reason", "version"},
    "gmail_action_failed": {"workspace_id", "command_id", "version"},
    "cleanup_proposal_created": {"workspace_id", "proposal_id", "message_id", "proposal_version"},
    "reminder_reactivated": {"workspace_id", "reminder_id", "message_id"},
}

# _integration-contract.md §2 lock_key 규칙: source-targeted job은 source_id별로
# lock한다(한 account에서 sync/watch churn 동시 실행 없음). execute_action은
# command_id별로 lock한다. message-level job(generate_summary, classify_importance,
# build_briefing 등)은 lock이 필요 없으며 idempotency_key만으로 충분하다.
_SOURCE_LOCKED_JOB_TYPES = {
    "register_watch",
    "renew_watch",
    "poll_history",
    "sync_delta",
    "sync_full",
    "purge_disconnected_source",
}


def _resolve_lock_key(job_type: str, payload: dict) -> str | None:
    if job_type in _SOURCE_LOCKED_JOB_TYPES:
        source_id = payload.get("source_id")
        return f"source:{source_id}" if source_id else None
    if job_type == "execute_action":
        command_id = payload.get("command_id")
        return f"command:{command_id}" if command_id else None
    return None


# 기본 동작: event payload를 변경 없이 단일 job으로 pass-through한다. 모든 job
# handler는 필요한 key만 읽으므로(fixed key set에 대한 dict access) event의 추가 key는
# 무해하다. (event_type, job_type) pair가 기본 1-event-to-1-job pass-through로 만들 수
# 없는 값이 필요할 때만 여기에 entry를 추가한다. 예: static key override 또는 실제
# fan-out(1 event -> N jobs, 예: event의 message_ids list에서 message_id별 job 하나).
def _override_reason_initial_connect(event_payload: dict) -> list[dict]:
    return [{**event_payload, "reason": "initial_connect"}]


def _fan_out_per_message_id(event_payload: dict) -> list[dict]:
    return [{"message_id": message_id} for message_id in event_payload["message_ids"]]


def _single_message_id_to_build_briefing_payload(event_payload: dict) -> list[dict]:
    # summary_completed/importance_classified는 단일 `message_id`를 담는다
    # (assistant_decisions는 job마다 message 하나를 평가). build_briefing의 payload
    # contract는 handler가 읽는 key인 복수형 `message_ids` list를 요구한다. element가
    # 1개뿐이어도 list여야 한다.
    return [
        {
            "workspace_id": event_payload["workspace_id"],
            "message_ids": [event_payload["message_id"]],
        }
    ]


def _optional_message_id_to_build_briefing_payload(event_payload: dict) -> list[dict]:
    # gmail_action_applied/gmail_action_undone의 message_id는 실제로 null일 수 있다
    # (하나의 message에 묶이지 않는 command, 예: 미래 bulk action). 항상 실제 message를
    # 평가하는 summary/importance와 다르다. message_id가 없으면 briefing이 rebuild할
    # 대상도 없으므로, handler에서 터질 message_ids: [None]으로 build_briefing을
    # enqueue하지 않고 job을 반환하지 않는다.
    if not event_payload.get("message_id"):
        return []
    return [
        {
            "workspace_id": event_payload["workspace_id"],
            "message_ids": [event_payload["message_id"]],
        }
    ]


def _skip_if_no_message_id(event_payload: dict) -> list[dict]:
    # 위와 같은 message-less-command guard를 reconcile_action에 적용한다.
    # message_id가 없으면 reconcile할 대상도 없다.
    if not event_payload.get("message_id"):
        return []
    return [dict(event_payload)]


def _wrap_for_emit_notification(event_type: str) -> Callable[[dict], list[dict]]:
    # emit_notification_job의 payload shape는 {"trigger": <event_type>,
    # "payload": <raw event payload>}이다(notifications/jobs/emit_notification.py).
    # event 자체의 payload dict뿐 아니라 *event_type 문자열 자체*가 payload 값으로
    # 필요하므로 generic pass-through만으로는 이 wrapper를 만들 수 없다. _PAYLOAD_BUILDERS
    # 값은 event_type 인자가 없는 Callable[[dict], list[dict]]이므로, 단일 parametrized
    # builder 대신 wired trigger마다 작은 closure 하나씩을 아래에 등록한다.
    def _builder(event_payload: dict) -> list[dict]:
        return [{"trigger": event_type, "payload": event_payload}]

    return _builder


_PAYLOAD_BUILDERS: dict[tuple[str, str], Callable[[dict], list[dict]]] = {
    ("gmail_source_connected", "sync_full"): _override_reason_initial_connect,
    ("gmail_snapshot_changed", "generate_summary"): _fan_out_per_message_id,
    ("gmail_snapshot_changed", "classify_importance"): _fan_out_per_message_id,
    ("summary_completed", "build_briefing"): _single_message_id_to_build_briefing_payload,
    ("importance_classified", "build_briefing"): _single_message_id_to_build_briefing_payload,
    ("gmail_action_applied", "build_briefing"): _optional_message_id_to_build_briefing_payload,
    ("gmail_action_undone", "build_briefing"): _optional_message_id_to_build_briefing_payload,
    ("gmail_action_applied", "reconcile_action"): _skip_if_no_message_id,
    ("reminder_reactivated", "build_briefing"): _optional_message_id_to_build_briefing_payload,
    # IC7 (알림 라우팅) — notifications.md의 route_target table이 이미 resolve하는
    # trigger 4개(service.py "Trigger scope note"). 나머지 3개(gmail_action_undone 및
    # gmail_snapshot_changed split 2개)는 unwired로 둔다. gmail_action_undone->
    # emit_notification은 별도 dedupe/UX 결정이 필요하고(IC4의 gmail_action_undone->
    # build_briefing으로 briefing rebuild는 이미 처리됨), 같은 docstring에 적힌 대로
    # snapshot_changed split은 mail_intake의 실제 payload에서 전혀 파생할 수 없다
    # (그 안에 importance signal 없음).
    ("gmail_source_recovery_needed", "emit_notification"): _wrap_for_emit_notification(
        "gmail_source_recovery_needed"
    ),
    ("gmail_action_failed", "emit_notification"): _wrap_for_emit_notification("gmail_action_failed"),
    ("cleanup_proposal_created", "emit_notification"): _wrap_for_emit_notification(
        "cleanup_proposal_created"
    ),
    ("reminder_reactivated", "emit_notification"): _wrap_for_emit_notification("reminder_reactivated"),
}


def _build_job_payloads(event_type: str, job_type: str, event_payload: dict) -> list[dict]:
    builder = _PAYLOAD_BUILDERS.get((event_type, job_type))
    if builder is None:
        return [dict(event_payload)]
    return builder(event_payload)


async def _enqueue_job(
    connection: AsyncConnection,
    *,
    job_type: str,
    payload: dict,
    idempotency_key: str,
    lock_key: str | None,
) -> uuid.UUID | None:
    stmt = (
        pg_insert(job_runs)
        .values(
            id=uuid.uuid4(),
            job_type=job_type,
            payload=payload,
            idempotency_key=idempotency_key,
            lock_key=lock_key,
            scheduled_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(constraint="uq_job_runs_job_type_idempotency_key")
        .returning(job_runs.c.id)
    )
    result = await connection.execute(stmt)
    row = result.first()
    return row.id if row is not None else None


async def dispatch_pending_events(
    connection: AsyncConnection, *, consumers: dict[str, list[str]]
) -> list[uuid.UUID]:
    """`consumers`에 따라 (pending outbox event, consumer job_type) pair마다
    job_runs row 하나를 queue한다(event_type -> job_type list; caller는
    app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS를 넘긴다. discovery.collect_event_consumers를
    쓰지 않는 이유는 module docstring 참고).

    consumer가 claim했는지와 무관하게 선택된 모든 event를 dispatched로 표시한다. 아직
    등록된 consumer가 없는 event type(IC-deferred trigger)은 error가 아니라 no-op이므로
    다음 poll에서 다시 선택되지 않는다.

    idempotency_key는 `event:{event_id}:job:{job_type}`이다. outbox event id는 새 random
    uuid가 아니라 실제 causal disambiguator이므로, 같은 pending row에 dispatch를 다시
    실행해도(예: 겹치는 poll tick 두 개) 같은 event에 대해 job_runs row를 중복 enqueue할 수 없다.
    """
    rows = (
        (
            await connection.execute(
                select(outbox_events)
                .where(outbox_events.c.status == "pending")
                .order_by(outbox_events.c.created_at)
            )
        )
        .mappings()
        .all()
    )

    enqueued_job_ids: list[uuid.UUID] = []
    for event in rows:
        for job_type in consumers.get(event["event_type"], []):
            try:
                job_payloads = _build_job_payloads(
                    event["event_type"], job_type, dict(event["payload"])
                )
            except KeyError as exc:
                # builder(_fan_out_per_message_id 등)가 event의 실제 payload가 충족하지
                # 못하는 payload[key] 직접 read를 했다. 아래 required-key check와 같은
                # "wiring bug는 dispatch 시점에 명확히 실패" 의도이며, generic post-check가
                # 아니라 builder 내부에서 발생했을 뿐이다.
                raise MissingJobPayloadKeyError(
                    f"{event['event_type']} -> {job_type} builder needs key {exc} "
                    f"(event_id={event['id']})"
                ) from exc
            for index, job_payload in enumerate(job_payloads):
                required = _REQUIRED_PAYLOAD_KEYS.get(job_type, set())
                # 단순 key 존재 여부가 아니라 value-level check다. required key가 있지만
                # null인 경우(예: producer가 key를 완전히 생략하는 대신
                # {"workspace_id": None}을 emit)는 missing key와 정확히 같은 방식으로
                # 실패해야 한다. downstream job handler가 uuid.UUID(str(None))을 실행하는
                # 것은 어느 쪽이든 같은 silent-retry-exhaustion failure다.
                missing = {key for key in required if job_payload.get(key) is None}
                if missing:
                    raise MissingJobPayloadKeyError(
                        f"{event['event_type']} -> {job_type} payload missing/null "
                        f"{sorted(missing)} (event_id={event['id']})"
                    )
                if job_type == "emit_notification":
                    inner_required = _EMIT_NOTIFICATION_REQUIRED_KEYS.get(
                        job_payload.get("trigger"), set()
                    )
                    inner_payload = job_payload.get("payload") or {}
                    inner_missing = {key for key in inner_required if inner_payload.get(key) is None}
                    if inner_missing:
                        raise MissingJobPayloadKeyError(
                            f"{event['event_type']} -> emit_notification payload missing/null "
                            f"{sorted(inner_missing)} (event_id={event['id']})"
                        )
                # fan-out event(job_payloads entry가 2개 이상)은 payload마다 서로 다른
                # idempotency_key가 필요하다. 그렇지 않으면 (job_type, idempotency_key)의
                # UNIQUE constraint 때문에 N개 중 첫 번째만 통과하고 나머지는 error 없이
                # 조용히 drop된다. "message_id" 같은 특정 key 이름의 우연한 존재가 아니라
                # 실제 fan-out 조건(len(job_payloads) > 1)으로 gate한다. 나중에 다른
                # key(action_id 등)를 기준으로 하는 fan-out builder가 single-payload branch로
                # 조용히 빠지면 안 된다.
                idempotency_key = f"event:{event['id']}:job:{job_type}"
                if len(job_payloads) > 1:
                    idempotency_key += f":{index}"
                job_id = await _enqueue_job(
                    connection,
                    job_type=job_type,
                    payload=job_payload,
                    idempotency_key=idempotency_key,
                    lock_key=_resolve_lock_key(job_type, job_payload),
                )
                if job_id is not None:
                    enqueued_job_ids.append(job_id)

        await connection.execute(
            update(outbox_events)
            .where(outbox_events.c.id == event["id"])
            .values(status="dispatched", dispatched_at=datetime.now(timezone.utc))
        )

    return enqueued_job_ids
