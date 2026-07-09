"""job_type=create_rule_suggestions, payload={correction_signal_id} —
_integration-contract.md §2. Triggered by label_correction_recorded (labels
domain). This task only wires and tests the handler function directly —
the outbox->job_runs dispatch wiring for label_correction_recorded is a
later integration step, per caller instructions."""

import uuid

from app.core.database import engine
from app.domains.assistant_decisions.rules import create_rule_suggestion_from_signal


async def create_rule_suggestions_job(payload: dict) -> None:
    correction_signal_id = uuid.UUID(str(payload["correction_signal_id"]))
    async with engine.begin() as connection:
        await create_rule_suggestion_from_signal(
            connection, correction_signal_id=correction_signal_id
        )
