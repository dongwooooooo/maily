import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=renew_watch, payload={source_id}.

    schedule에 따라 watch expiration 전에 trigger된다. expiring source를 선택하는 scheduler는
    `repository.list_watches_expiring_before`이며, source별로 이 job을 enqueue하는 cron
    wiring이 이를 호출한다(Task 4/5 범위 밖, mail_intake.md renew_watch 참고).
    """
    connected_account_id = uuid.UUID(payload["source_id"])
    async with engine.begin() as connection:
        await service.renew_watch(connection, connected_account_id=connected_account_id)
