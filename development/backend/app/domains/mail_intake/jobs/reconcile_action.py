import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=reconcile_action, payload={message_id, add_label_ids?,
    remove_label_ids?}. Triggered by gmail_action_applied (IC4,
    _build-schedule.md "mail_intake snapshot reconcile")."""
    message_id = uuid.UUID(payload["message_id"])
    async with engine.begin() as connection:
        await service.reconcile_action_labels(
            connection,
            message_id=message_id,
            add_label_ids=payload.get("add_label_ids") or [],
            remove_label_ids=payload.get("remove_label_ids") or [],
        )
