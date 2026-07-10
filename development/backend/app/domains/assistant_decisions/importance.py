"""Job: classify_importance — assistant_decisions.md "Job: classify_importance".

generate_summary와 독립적으로 실행된다. 별도 job_type, 별도 table
(importance_jobs / message_importance_classifications), 별도 try/except를 사용하므로
한쪽의 failure/retry가 다른 쪽 row를 건드리지 않는다. "pending"은 별도 pending
flag/column이 아니라 "message_importance_classifications에 row 없음"으로 표현한다
(module-boundaries.md 흐름 2).
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import MailyError
from app.core.outbox import append_event
from app.domains.assistant_decisions import events, repository, service
from app.domains.assistant_decisions.llm import get_llm

logger = structlog.get_logger()


async def run_classify_importance(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict | None:
    message = await service.get_message_or_404(connection, message_id=message_id)
    scope = await service.resolve_message_scope_or_404(connection, message_id=message_id)
    # snapshot 존재가 유일한 precondition이다. summary와 달리 summary_enabled와 무관하게
    # 실행된다(importance는 privacy-sensitive summary surface가 아니라 briefing sort를 구동).

    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    await repository.insert_importance_job(
        connection, job_id=job_id, message_id=message_id, created_at=now
    )
    await repository.mark_importance_job_running(connection, job_id=job_id)

    payload = await service.build_importance_payload(connection, message=message)

    try:
        outcome = get_llm().classify_importance(payload)
    except MailyError as exc:
        await repository.mark_importance_job_failed(
            connection, job_id=job_id, finished_at=datetime.now(timezone.utc)
        )
        logger.warning("메일 중요도 판단 실패", message_id=str(message_id), reason=str(exc))
        return None

    classification_row = await repository.upsert_message_importance_classification(
        connection,
        message_id=message_id,
        importance_band=outcome["importance_band"],
        reason=outcome["reason"],
    )
    await repository.mark_importance_job_succeeded(
        connection, job_id=job_id, finished_at=datetime.now(timezone.utc)
    )
    await append_event(
        connection,
        event_type=events.IMPORTANCE_CLASSIFIED,
        producer_domain="assistant_decisions",
        payload={
            "message_id": str(message_id),
            "workspace_id": str(scope["workspace_id"]),
            "importance_band": classification_row["importance_band"],
            "reason": classification_row["reason"],
            "classification_version": classification_row["classification_version"],
        },
        idempotency_key=events.importance_classified_key(
            message_id, classification_row["classification_version"]
        ),
    )
    logger.info(
        "메일 중요도 판단 완료",
        message_id=str(message_id),
        importance_band=classification_row["importance_band"],
        classification_version=classification_row["classification_version"],
    )
    return classification_row


def to_public_view(classification: dict, *, include_reason: bool = False) -> dict:
    """API 응답 기본값에서 reason 제외 — 최상위 원칙 "AI 판단 이유는 기본으로
    노출하지 않는다". reason이 필요한 caller(예: 미래의 "왜?" UI affordance)는
    include_reason=True를 명시적으로 넘긴다."""
    view = {
        "id": classification["id"],
        "message_id": classification["message_id"],
        "importance_band": classification["importance_band"],
        "classification_version": classification["classification_version"],
    }
    if include_reason:
        view["reason"] = classification["reason"]
    return view
