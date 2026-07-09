from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=process_notification, payload={email_address, history_id,
    notification_id}. Triggered by the Pub/Sub webhook (POST
    /intake/pubsub)."""
    async with engine.begin() as connection:
        await service.process_notification(
            connection,
            email_address=payload["email_address"],
            history_id=int(payload["history_id"]),
            notification_id=payload.get("notification_id"),
        )
