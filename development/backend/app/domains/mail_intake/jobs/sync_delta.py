import uuid

from app.core.database import engine
from app.domains.mail_intake import service


async def handle(payload: dict) -> None:
    """job_type=sync_delta, payload={source_id, start_history_id}.

    gmail_notification_received(dedupe됨) 또는 poll_history fallback이 trigger한다. `trigger`는
    job_registry payload shape(_integration-contract.md §2)의 일부가 아니므로 여기서는
    "notification"으로 infer한다. sync_runs.trigger에 "poll"을 기록해야 하는 caller는 이 job
    wrapper를 거치지 말고 trigger="poll"로 service.sync_delta를 직접 호출해야 한다
    (poll_history.py는 현재 service.poll_history를 호출하고, 이 함수가 notification-shaped
    payload로 이 job을 enqueue한다).
    """
    connected_account_id = uuid.UUID(payload["source_id"])
    start_history_id = int(payload["start_history_id"])
    async with engine.begin() as connection:
        await service.sync_delta(
            connection,
            connected_account_id=connected_account_id,
            start_history_id=start_history_id,
            trigger=payload.get("trigger", "notification"),
        )
