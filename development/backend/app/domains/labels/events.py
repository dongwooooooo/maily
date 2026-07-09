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
    """Emit label_correction_recorded for a newly written correction signal.

    idempotency key per module-boundaries.md Event Catalog:
    message:{message_id}:label:{label_id}:correction:{version} — version
    is the append-only occurrence count for this (message_id,
    service_label_id) pair, not a random disambiguator.

    Consumer (assistant_decisions create_rule_suggestions) only needs
    correction_signal_id per _integration-contract.md §2 job payload
    shape; message_id/service_label_id are included too for any other
    consumer or debugging use.
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
