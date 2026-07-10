"""job_type=generate_summary, payload={message_id} — _integration-contract.md
§2. summary_enabled일 때 gmail_snapshot_changed가 trigger한다(dispatcher wiring은 이후
integration step. 이 task는 handler function만 wire하고 직접 test한다. gmail_actions
Task 9의 execute_action.py와 같은 scope note)."""

import uuid

from app.core.database import engine
from app.domains.assistant_decisions.summaries import run_generate_summary


async def generate_summary_job(payload: dict) -> None:
    message_id = uuid.UUID(str(payload["message_id"]))
    async with engine.begin() as connection:
        await run_generate_summary(connection, message_id=message_id)
