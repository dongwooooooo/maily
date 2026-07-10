"""job_type=classify_importance, payload={message_id} —
_integration-contract.md §2. Triggered by gmail_snapshot_changed
unconditionally (dispatcher wiring is a later integration step)."""

import uuid

from app.core.database import engine
from app.domains.assistant_decisions.importance import run_classify_importance


async def classify_importance_job(payload: dict) -> None:
    message_id = uuid.UUID(str(payload["message_id"]))
    async with engine.begin() as connection:
        await run_classify_importance(connection, message_id=message_id)
