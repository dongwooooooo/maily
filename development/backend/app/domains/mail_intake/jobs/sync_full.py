import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=sync_full, payload={source_id, reason}.

    cursor invalidation 또는 initial connection이 trigger한다(gmail_source_connected가
    register_watch와 함께 queue).
    """
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.sync_full(
            connection,
            connected_account_id=connected_account_id,
            reason=payload.get("reason", "manual"),
        )
