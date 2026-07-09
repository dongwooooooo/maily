import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=renew_watch, payload={source_id}. Triggered on a schedule
    (before watch expiration) — the scheduler that selects which sources
    are expiring is `repository.list_watches_expiring_before`, called by
    whatever cron wiring enqueues one of these jobs per source (out of
    Task 4/5 scope; see mail_intake.md renew_watch)."""
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.renew_watch(connection, connected_account_id=connected_account_id)
