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


# Default behavior: pass the event payload through unchanged — every job
# handler reads only the keys it needs (dict access on a fixed key set), so
# extra keys from the event are harmless. Only add an entry here when a job
# needs a key the event genuinely doesn't carry.
_PAYLOAD_OVERRIDES: dict[tuple[str, str], dict] = {
    ("gmail_source_connected", "sync_full"): {"reason": "initial_connect"},
}


def _build_job_payload(event_type: str, job_type: str, event_payload: dict) -> dict:
    override = _PAYLOAD_OVERRIDES.get((event_type, job_type))
    if override is None:
        return dict(event_payload)
    return {**event_payload, **override}


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
            job_payload = _build_job_payload(event["event_type"], job_type, dict(event["payload"]))
            missing = _REQUIRED_PAYLOAD_KEYS.get(job_type, set()) - job_payload.keys()
            if missing:
                raise MissingJobPayloadKeyError(
                    f"{event['event_type']} -> {job_type} payload missing {sorted(missing)} "
                    f"(event_id={event['id']})"
                )
            job_id = await _enqueue_job(
                connection,
                job_type=job_type,
                payload=job_payload,
                idempotency_key=f"event:{event['id']}:job:{job_type}",
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
