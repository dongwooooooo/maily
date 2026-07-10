import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.outbox import append_event

LABEL_CORRECTION_RECORDED = "label_correction_recorded"


async def record_label_correction_recorded(
    connection: AsyncConnection,
    *,
    signal_id: uuid.UUID,
    message_id: uuid.UUID,
    service_label_id: uuid.UUID,
    version: int,
) -> uuid.UUID | None:
    """새로 작성된 correction signal에 대해 label_correction_recorded를 emit한다.

    module-boundaries.md Event Catalog 기준 idempotency key:
    message:{message_id}:label:{label_id}:correction:{version}. version은 random
    disambiguator가 아니라 이 (message_id, service_label_id) pair의 append-only occurrence
    count다.

    consumer(assistant_decisions create_rule_suggestions)는 _integration-contract.md §2 job
    payload shape 기준 correction_signal_id만 필요로 한다. 다른 consumer나 debugging 용도를 위해
    message_id/service_label_id도 함께 포함한다.
    """
    return await append_event(
        connection,
        event_type=LABEL_CORRECTION_RECORDED,
        producer_domain="labels",
        payload={
            "correction_signal_id": str(signal_id),
            "message_id": str(message_id),
            "service_label_id": str(service_label_id),
        },
        idempotency_key=f"message:{message_id}:label:{service_label_id}:correction:{version}",
    )
