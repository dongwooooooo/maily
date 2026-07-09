"""job_type=generate_summary, payload={message_id} — _integration-contract.md
§2. Triggered by gmail_snapshot_changed when summary_enabled (dispatcher
wiring is a later integration step — this task only wires the handler
function and tests it directly, same scope note as gmail_actions Task 9's
execute_action.py)."""

import uuid

from app.core.database import engine
from app.domains.assistant_decisions.summaries import run_generate_summary


async def generate_summary_job(payload: dict) -> None:
    message_id = uuid.UUID(str(payload["message_id"]))
    async with engine.begin() as connection:
        await run_generate_summary(connection, message_id=message_id)
