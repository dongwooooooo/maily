import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=poll_history, payload={source_id}.

    watch/notification delivery가 조용해졌을 수 있을 때 fallback safety net으로 schedule에 따라
    trigger된다.
    """
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.poll_history(connection, connected_account_id=connected_account_id)
