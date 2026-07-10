import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.domains.identity.schemas import RequestContext
from app.domains.mail_intake import repository, service
from app.domains.mail_intake.schemas import ManualSyncQueued, ManualSyncRequest, PubSubAckResponse
from app.domains.mail_sources import repository as mail_sources_repository

router = APIRouter()


@router.post("/pubsub", response_model=PubSubAckResponse, status_code=200)
async def pubsub_webhook(
    request: Request,
    connection: AsyncConnection = Depends(get_db_connection),
) -> PubSubAckResponse:
    """Pub/Sub push webhook.

    auth가 통과하면 항상 200으로 ack한다. duplicate 또는 orphan(matching active source 없음)
    notification도 error가 아니라 normal outcome이므로(mail_intake.md "[멱등]"/"[빈상태]"),
    Pub/Sub이 retry storm을 만들지 않는다.
    """
    if settings.pubsub_webhook_token:
        auth_header = request.headers.get("authorization", "")
        token = (
            auth_header.removeprefix("Bearer ") if auth_header.startswith("Bearer ") else ""
        )
        if token != settings.pubsub_webhook_token:
            raise UnauthorizedError("invalid pubsub webhook token")

    body = await request.json()
    message = body.get("message") or {}
    data_b64 = message.get("data")
    if not data_b64:
        raise ValidationError("missing pubsub message data")
    try:
        decoded = json.loads(base64.b64decode(data_b64))
    except Exception as exc:
        raise ValidationError("invalid pubsub message data") from exc

    email_address = decoded.get("emailAddress")
    history_id = decoded.get("historyId")
    if not email_address or history_id is None:
        raise ValidationError("pubsub payload missing emailAddress/historyId")

    result = await service.process_notification(
        connection,
        email_address=email_address,
        history_id=int(history_id),
        notification_id=message.get("messageId"),
    )
    return PubSubAckResponse(deduped=result["deduped"])


@router.post("/sources/{source_id}/sync", response_model=ManualSyncQueued, status_code=202)
async def manual_sync(
    source_id: uuid.UUID,
    body: ManualSyncRequest,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> ManualSyncQueued:
    """manual resync trigger.

    route는 이 router의 /intake prefix(app/api/router.py) 아래 mount되어
    POST /intake/sources/{id}/sync가 된다. _integration-contract.md §3의 literal path
    ("POST /sources/{id}/sync", /intake prefix 없음)를 쓰려면 `router`를 두 exposed symbol로
    나눠야 하는데, §4의 single-`router`-per-domain contract가 이를 허용하지 않는다.
    자세한 이유는 이 domain의 final report 참고.
    """
    account = await mail_sources_repository.get_connected_account(
        connection, connected_account_id=source_id
    )
    if account is None or account["workspace_id"] != context.workspace_id:
        raise NotFoundError("gmail source not found")
    if account["status"] in ("disconnecting", "disconnected"):
        raise ConflictError("gmail source is disconnecting or disconnected")

    settings_row = await mail_sources_repository.get_source_settings(
        connection, connected_account_id=source_id
    )
    if settings_row is not None and settings_row["paused"]:
        raise ConflictError("gmail source is paused")

    now = datetime.now(timezone.utc)
    cursor = await repository.get_cursor(connection, connected_account_id=source_id)
    # 아직 cursor가 없다는 것은 이 source가 sync를 완료한 적이 없다는 뜻이다.
    # "delta" request가 기준으로 삼을 대상이 없으므로 caller 요청과 무관하게 full로 promote한다.
    if body.run_type == "full" or cursor is None or cursor["last_history_id"] is None:
        job_type = "sync_full"
        payload = {"source_id": str(source_id), "reason": "manual"}
        idempotency_key = f"sync-full:{source_id}:manual:{uuid.uuid4()}"
    else:
        start_history_id = cursor["last_history_id"]
        job_type = "sync_delta"
        payload = {"source_id": str(source_id), "start_history_id": start_history_id}
        idempotency_key = f"sync-delta:{source_id}:manual:{start_history_id}:{uuid.uuid4()}"

    job_id = await repository.enqueue_job(
        connection,
        job_type=job_type,
        payload=payload,
        idempotency_key=idempotency_key,
        lock_key=f"source:{source_id}",
        scheduled_at=now,
    )
    return ManualSyncQueued(source_id=source_id, job_type=job_type, queued=job_id is not None)
