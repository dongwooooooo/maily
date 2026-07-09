"""job_type=prepare_cleanup_proposals, payload={workspace_id, message_ids?} —
_integration-contract.md §2. Triggered by gmail_snapshot_changed (dispatcher
wiring deferred, same scope note as the other jobs in this module)."""

import uuid

from app.core.database import engine
from app.core.errors import ValidationError
from app.domains.assistant_decisions.cleanup import prepare_cleanup_proposals


async def prepare_cleanup_proposals_job(payload: dict) -> None:
    workspace_id = uuid.UUID(str(payload["workspace_id"]))
    message_ids = [uuid.UUID(str(m)) for m in payload.get("message_ids") or []]
    # No system/service account exists in this POC — the job's own
    # workspace_id doubles as `requested_by` is not valid (that field is a
    # users.id FK). Callers driving this job directly in tests pass
    # requested_by explicitly via cleanup.prepare_cleanup_proposals instead;
    # the event-triggered path (auto-apply with no human actor) is an open
    # question for the coordinator — see task report.
    if "requested_by" not in payload:
        raise ValidationError("requested_by is required in prepare_cleanup_proposals payload")
    requested_by = uuid.UUID(str(payload["requested_by"]))
    async with engine.begin() as connection:
        await prepare_cleanup_proposals(
            connection,
            workspace_id=workspace_id,
            message_ids=message_ids,
            requested_by=requested_by,
        )
