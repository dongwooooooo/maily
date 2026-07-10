"""job_type=prepare_cleanup_proposals, payload={workspace_id, message_ids?} —
_integration-contract.md §2. gmail_snapshot_changed가 trigger한다(dispatcher wiring은
deferred이며, 이 module의 다른 job과 같은 scope note)."""

import uuid

from app.core.database import engine
from app.core.errors import ValidationError
from app.domains.assistant_decisions.cleanup import prepare_cleanup_proposals


async def prepare_cleanup_proposals_job(payload: dict) -> None:
    workspace_id = uuid.UUID(str(payload["workspace_id"]))
    message_ids = [uuid.UUID(str(m)) for m in payload.get("message_ids") or []]
    # 이 POC에는 system/service account가 없다. job 자체의 workspace_id를 `requested_by`로
    # 겸용하는 것은 유효하지 않다(해당 field는 users.id FK). test에서 이 job을 직접 구동하는
    # caller는 대신 cleanup.prepare_cleanup_proposals를 통해 requested_by를 명시적으로 넘긴다.
    # event-triggered path(사람 actor 없는 auto-apply)는 coordinator open question이다.
    # task report 참고.
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
