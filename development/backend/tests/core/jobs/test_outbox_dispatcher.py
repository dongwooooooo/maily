import uuid

import pytest
from sqlalchemy import insert, select, update

from app.core.database import engine
from app.core.jobs.models import job_runs
from app.core.jobs.outbox_dispatcher import MissingJobPayloadKeyError, dispatch_pending_events
from app.core.outbox import append_event, outbox_events


async def _seed_event(event_type: str, payload: dict, idempotency_key: str | None = None) -> uuid.UUID:
    async with engine.begin() as connection:
        event_id = await append_event(
            connection,
            event_type=event_type,
            producer_domain="test",
            payload=payload,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )
    return event_id


async def test_dispatches_one_job_per_consumer_job_type() -> None:
    """[정상] event_type이 job_type 2개에 매핑되면 job_runs에 2행 큐잉."""
    source_id = str(uuid.uuid4())
    await _seed_event("gmail_source_connected", {"source_id": source_id, "workspace_id": str(uuid.uuid4())})

    async with engine.begin() as connection:
        enqueued = await dispatch_pending_events(
            connection, consumers={"gmail_source_connected": ["register_watch", "sync_full"]}
        )

    assert len(enqueued) == 2
    async with engine.connect() as connection:
        rows = (
            (await connection.execute(select(job_runs).where(job_runs.c.id.in_(enqueued))))
            .mappings()
            .all()
        )
    job_types = {r["job_type"] for r in rows}
    assert job_types == {"register_watch", "sync_full"}
    register_watch_row = next(r for r in rows if r["job_type"] == "register_watch")
    assert register_watch_row["payload"]["source_id"] == source_id
    assert register_watch_row["lock_key"] == f"source:{source_id}"
    sync_full_row = next(r for r in rows if r["job_type"] == "sync_full")
    assert sync_full_row["payload"]["reason"] == "initial_connect"


async def test_event_with_no_registered_consumer_is_noop_not_error() -> None:
    """[정상] IC-미배선 트리거는 조용히 dispatched 처리만 되고 job_runs 생성 없음."""
    await _seed_event("some_future_event", {"foo": "bar"})

    async with engine.begin() as connection:
        enqueued = await dispatch_pending_events(connection, consumers={})

    assert enqueued == []
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    select(outbox_events).where(outbox_events.c.event_type == "some_future_event")
                )
            )
            .mappings()
            .all()
        )
    assert rows[0]["status"] == "dispatched"


async def test_dispatched_events_are_not_redispatched() -> None:
    """[멱등] 이미 dispatched된 event는 다음 poll에서 다시 선택되지 않는다."""
    await _seed_event("gmail_source_connected", {"source_id": str(uuid.uuid4())})

    async with engine.begin() as connection:
        first = await dispatch_pending_events(connection, consumers={"gmail_source_connected": ["register_watch"]})
        second = await dispatch_pending_events(connection, consumers={"gmail_source_connected": ["register_watch"]})

    assert len(first) == 1
    assert second == []


async def test_rerunning_dispatch_over_same_pending_row_does_not_double_enqueue() -> None:
    """[동시] 같은 event가 아직 pending인 상태에서 dispatch가 두 번 겹쳐 돌아도
    job_runs는 event+job_type 조합당 하나만 남는다(idempotency_key dedupe)."""
    source_id = str(uuid.uuid4())
    event_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(outbox_events).values(
                id=event_id,
                event_type="gmail_source_connected",
                producer_domain="test",
                payload={"source_id": source_id},
                idempotency_key=str(uuid.uuid4()),
                status="pending",
            )
        )

    # 두 overlapping dispatch pass가 둘 중 어느 쪽도 dispatched로 표시하기 전에 같은 row를
    # pending으로 본 상황을 흉내낸다. 같은 idempotency_key로 enqueue step을 직접 두 번 호출한다.
    from app.core.jobs.outbox_dispatcher import _enqueue_job

    async with engine.begin() as connection:
        first = await _enqueue_job(
            connection,
            job_type="register_watch",
            payload={"source_id": source_id},
            idempotency_key=f"event:{event_id}:job:register_watch",
            lock_key=f"source:{source_id}",
        )
        second = await _enqueue_job(
            connection,
            job_type="register_watch",
            payload={"source_id": source_id},
            idempotency_key=f"event:{event_id}:job:register_watch",
            lock_key=f"source:{source_id}",
        )

    assert first is not None
    assert second is None

    # outbox row를 현실적인 post-dispatch state로 남긴다. 여기서 'pending' row가 남으면
    # 이후 test의 dispatch_pending_events() call이 이를 주워갈 수 있다(shared Postgres,
    # suite 전체에서 per-test rollback 없음).
    async with engine.begin() as connection:
        await connection.execute(
            update(outbox_events).where(outbox_events.c.id == event_id).values(status="dispatched")
        )


async def test_emit_notification_wrapped_payload_null_field_fails_loud_at_dispatch() -> None:
    """[IC7 코드리뷰 Major] emit_notification의 job payload는
    {"trigger":..., "payload":{...}} wrapper라 top-level _REQUIRED_PAYLOAD_KEYS
    체크만으론 안쪽 dict를 못 본다 — trigger별 내부 필드 검증이 실제로 동작하는지
    확인. reminder_reactivated는 message_id가 필수인데 없는 payload로 dispatch."""
    event_id = await _seed_event(
        "reminder_reactivated",
        {"workspace_id": str(uuid.uuid4()), "reminder_id": str(uuid.uuid4())},  # message_id 없음
    )

    with pytest.raises(MissingJobPayloadKeyError):
        async with engine.begin() as connection:
            await dispatch_pending_events(
                connection, consumers={"reminder_reactivated": ["emit_notification"]}
            )

    # raise 때문에 dispatch 자체 transaction이 rollback되어 seeded event는 여전히
    # 'pending'이다. 그대로 두면 이후 test의 dispatch_pending_events() call(shared Postgres,
    # per-test rollback 없음)이 같은 raise를 예기치 않게 다시 trigger할 수 있다.
    # 직접 dispatched로 표시한다.
    async with engine.begin() as connection:
        await connection.execute(
            update(outbox_events).where(outbox_events.c.id == event_id).values(status="dispatched")
        )
