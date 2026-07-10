"""job_type=create_rule_suggestions, payload={correction_signal_id} —
_integration-contract.md §2. label_correction_recorded(labels domain)가 trigger한다.
caller 지시에 따라 이 task는 handler function만 직접 wire/test한다.
label_correction_recorded의 outbox->job_runs dispatch wiring은 이후 integration step이다."""

import uuid

from app.core.database import engine
from app.domains.assistant_decisions.rules import create_rule_suggestion_from_signal


async def create_rule_suggestions_job(payload: dict) -> None:
    correction_signal_id = uuid.UUID(str(payload["correction_signal_id"]))
    async with engine.begin() as connection:
        await create_rule_suggestion_from_signal(
            connection, correction_signal_id=correction_signal_id
        )
