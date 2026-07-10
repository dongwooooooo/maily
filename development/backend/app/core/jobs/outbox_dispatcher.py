"""Outbox -> job_runs dispatcher — _integration-contract.md §3.

Reads pending outbox_events, looks up which job_type(s) each event_type
should queue, enqueues one job_runs row per (event, job_type) pair, and
marks the event dispatched. Producer domains never call a consumer
directly — this module is the one place that crosses that boundary, and
it does so generically (event_type -> job_type string lookup), never
importing a domain's service/job function.

Callers MUST pass `app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS` (or a
narrower subset), NOT `app.core.discovery.collect_event_consumers(...)`.
The discovery map is every domain's *declared* contract intent, including
entries domains have explicitly flagged as not really wired yet; the
wiring module is the curated subset actually proven safe to dispatch, one
IC checkpoint at a time — see wiring.py's docstring for why (event-type
payload shapes that need N-way fan-out, like gmail_snapshot_changed's
message_ids list, can't go through this generic 1-event-to-1-job pass-
through at all).
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
    """Raised when a wired (event_type, job_type) pair would enqueue a
    job_runs row missing a key that job_type's handler requires. This is
    a wiring bug (a wiring.ACTIVE_EVENT_CONSUMERS entry added without a
    matching payload shape), not a data problem — it should fail loudly
    at dispatch time instead of silently queuing a job that will only
    fail once a worker picks it up."""


# Minimal required-key backstop for job_types currently reachable through
# wiring.ACTIVE_EVENT_CONSUMERS. Extend this alongside each new IC entry —
# it is not a full payload-shape validator, just a cheap guard against the
# exact failure mode found in IC1 review: a wired pair whose event payload
# doesn't actually carry a key the job handler does `payload["key"]` on.
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

# emit_notification's job payload is a wrapper — {"trigger": event_type,
# "payload": {...}} — so the generic _REQUIRED_PAYLOAD_KEYS check (which
# looks at top-level keys) can't validate it: the fields that actually
# matter live one level down, and which fields are required depends on
# which trigger produced the event (notifications.service.resolve_route_
# target's per-trigger branches). workspace_id is required for every
# trigger (emit_notification's own unconditional check); the rest mirror
# resolve_route_target exactly.
_EMIT_NOTIFICATION_REQUIRED_KEYS: dict[str, set[str]] = {
    "gmail_source_recovery_needed": {"workspace_id", "source_id", "reason", "version"},
    "gmail_action_failed": {"workspace_id", "command_id", "version"},
    "cleanup_proposal_created": {"workspace_id", "proposal_id", "message_id", "proposal_version"},
    "reminder_reactivated": {"workspace_id", "reminder_id", "message_id"},
}

# _integration-contract.md §2 lock_key rules: source-targeted jobs lock per
# source_id (no concurrent sync/watch churn on one account); execute_action
# locks per command_id; message-level jobs (generate_summary,
# classify_importance, build_briefing, ...) need no lock — idempotency_key
# alone is enough.
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


# Default behavior: pass the event payload through unchanged, as a single
# job — every job handler reads only the keys it needs (dict access on a
# fixed key set), so extra keys from the event are harmless. Only add an
# entry here when a (event_type, job_type) pair needs something the
# default 1-event-to-1-job pass-through can't produce: a static key
# override, or a real fan-out (1 event -> N jobs, e.g. one job per
# message_id in an event's message_ids list).
def _override_reason_initial_connect(event_payload: dict) -> list[dict]:
    return [{**event_payload, "reason": "initial_connect"}]


def _fan_out_per_message_id(event_payload: dict) -> list[dict]:
    return [{"message_id": message_id} for message_id in event_payload["message_ids"]]


def _single_message_id_to_build_briefing_payload(event_payload: dict) -> list[dict]:
    # summary_completed/importance_classified carry a single `message_id`
    # (assistant_decisions evaluates one message per job); build_briefing's
    # payload contract wants the plural `message_ids` list — even a
    # 1-element one — since that's the key its handler reads.
    return [
        {
            "workspace_id": event_payload["workspace_id"],
            "message_ids": [event_payload["message_id"]],
        }
    ]


def _optional_message_id_to_build_briefing_payload(event_payload: dict) -> list[dict]:
    # gmail_action_applied/gmail_action_undone's message_id can genuinely
    # be null (a command not tied to one message, e.g. a future bulk
    # action) — unlike summary/importance which always evaluate a real
    # message. No message_id means nothing for briefing to rebuild, so
    # this returns no job rather than enqueuing build_briefing with a
    # message_ids: [None] that would blow up in the handler.
    if not event_payload.get("message_id"):
        return []
    return [
        {
            "workspace_id": event_payload["workspace_id"],
            "message_ids": [event_payload["message_id"]],
        }
    ]


def _skip_if_no_message_id(event_payload: dict) -> list[dict]:
    # Same message-less-command guard as above, for reconcile_action —
    # nothing to reconcile without a message_id.
    if not event_payload.get("message_id"):
        return []
    return [dict(event_payload)]


def _wrap_for_emit_notification(event_type: str) -> Callable[[dict], list[dict]]:
    # emit_notification_job's payload shape is {"trigger": <event_type>,
    # "payload": <raw event payload>} (notifications/jobs/emit_notification.py) —
    # a wrapper the generic pass-through can't produce on its own, since it
    # needs the *event_type string itself* as a payload value, not just
    # the event's own payload dict. One tiny closure per wired trigger
    # (registered below) instead of a single parametrized builder, since
    # _PAYLOAD_BUILDERS values are Callable[[dict], list[dict]] with no
    # event_type argument.
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
    # IC7 (알림 라우팅) — the 4 triggers notifications.md's route_target
    # table already resolves (service.py "Trigger scope note"): the other
    # 3 (gmail_action_undone, and the two gmail_snapshot_changed splits)
    # stay unwired — gmail_action_undone->emit_notification would need
    # its own dedupe/UX decision (already covered for briefing rebuild by
    # IC4's gmail_action_undone->build_briefing), and the snapshot_changed
    # splits aren't derivable from mail_intake's actual payload at all
    # (no importance signal in it) per that same docstring.
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
    """Queue one job_runs row per (pending outbox event, consumer job_type)
    pair, per `consumers` (event_type -> job_type list; callers pass
    app.core.jobs.wiring.ACTIVE_EVENT_CONSUMERS — see module docstring for
    why not discovery.collect_event_consumers).

    Marks every selected event dispatched regardless of whether any
    consumer claimed it — an event type with no registered consumer yet
    (an IC-deferred trigger) is a no-op, not an error, so it doesn't get
    re-selected on the next poll.

    idempotency_key is `event:{event_id}:job:{job_type}` — the outbox
    event id is a real causal disambiguator (not a fresh random uuid), so
    re-running dispatch over the same pending rows (e.g. two overlapping
    poll ticks) can't double-enqueue a job_runs row for the same event.
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
                # A builder (_fan_out_per_message_id etc.) did a direct
                # payload[key] read the event's actual payload didn't
                # satisfy — same "wiring bug, fail loud at dispatch time"
                # intent as the required-key check below, just raised from
                # inside a builder instead of the generic post-check.
                raise MissingJobPayloadKeyError(
                    f"{event['event_type']} -> {job_type} builder needs key {exc} "
                    f"(event_id={event['id']})"
                ) from exc
            for index, job_payload in enumerate(job_payloads):
                required = _REQUIRED_PAYLOAD_KEYS.get(job_type, set())
                # Value-level check, not just key presence: a required key
                # present but null (e.g. a producer emitting
                # {"workspace_id": None} instead of omitting the key
                # entirely) must fail exactly the same way as a missing
                # key — a downstream job handler doing uuid.UUID(str(None))
                # is the same silent-retry-exhaustion failure either way.
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
                # A fan-out event (job_payloads has >1 entry) needs a
                # distinct idempotency_key per payload, or the UNIQUE
                # constraint on (job_type, idempotency_key) would let only
                # the first of N through — silently dropping the rest, no
                # error. Gate this on the actual fan-out condition
                # (len(job_payloads) > 1), not on a specific key name like
                # "message_id" happening to be present — a future fan-out
                # builder keyed on something else (action_id, etc.) must
                # not silently fall through to the single-payload branch.
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
