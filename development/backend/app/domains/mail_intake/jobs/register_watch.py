import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=register_watch, payload={source_id}. Triggered by
    gmail_source_connected (see _integration-contract.md §2/§3)."""
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.register_watch(connection, connected_account_id=connected_account_id)
