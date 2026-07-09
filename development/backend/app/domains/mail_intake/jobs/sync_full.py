import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=sync_full, payload={source_id, reason}. Triggered by cursor
    invalidation or an initial connection (queued alongside register_watch
    by gmail_source_connected)."""
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.sync_full(
            connection,
            connected_account_id=connected_account_id,
            reason=payload.get("reason", "manual"),
        )
