import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=poll_history, payload={source_id}. Triggered on a schedule
    as a fallback safety net when watch/notification delivery may have
    gone quiet."""
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.poll_history(connection, connected_account_id=connected_account_id)
