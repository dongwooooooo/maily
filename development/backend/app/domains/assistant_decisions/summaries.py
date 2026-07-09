"""Job: generate_summary — assistant_decisions.md "Job: generate_summary".

G6 privacy contract (critical): the LLM payload built here is
subject/sender/snippet/labels/excerpt only (service.build_summary_payload),
never a raw message body or a freeform prompt string — enforced structurally
by llm.SummaryInput's field set, not just by convention. summary_jobs and
message_summaries have no body/prompt column (models.py) — there is nowhere
to persist one even if a caller tried.
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


async def run_generate_summary(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    """Returns the upserted message_summaries row, or None if this account
    has summary disabled — in which case NO summary_jobs row is created
    either (assistant_decisions.md "job 자체를 만들지 않는다")."""
    message = await service.get_message_or_404(connection, message_id=message_id)
    scope = await service.resolve_message_scope_or_404(connection, message_id=message_id)

    summary_enabled = await repository.get_summary_enabled(
        connection, connected_account_id=scope["connected_account_id"]
    )
    if not summary_enabled:
        logger.info("요약 기능 꺼짐 — summary job 생성 안 함", message_id=str(message_id))
        return None

    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    await repository.insert_summary_job(connection, job_id=job_id, message_id=message_id, created_at=now)
    await repository.mark_summary_job_running(connection, job_id=job_id)

    payload = await service.build_summary_payload(connection, message=message)

    try:
        outcome = get_llm().summarize(payload)
    except MailyError as exc:
        await repository.mark_summary_job_failed(
            connection, job_id=job_id, finished_at=datetime.now(timezone.utc)
        )
        logger.warning("메일 요약 실패", message_id=str(message_id), reason=str(exc))
        return None

    summary_row = await repository.upsert_message_summary(
        connection,
        message_id=message_id,
        summary_text=outcome["summary_text"],
        is_metadata_only=outcome["is_metadata_only"],
        model_name=outcome["model_name"],
    )
    await repository.mark_summary_job_succeeded(
        connection, job_id=job_id, finished_at=datetime.now(timezone.utc)
    )
    await append_event(
        connection,
        event_type=events.SUMMARY_COMPLETED,
        producer_domain="assistant_decisions",
        payload={
            "message_id": str(message_id),
            "workspace_id": str(scope["workspace_id"]),
            "summary_version": summary_row["summary_version"],
            "is_metadata_only": summary_row["is_metadata_only"],
        },
        idempotency_key=events.summary_completed_key(message_id, summary_row["summary_version"]),
    )
    logger.info(
        "메일 요약 완료",
        message_id=str(message_id),
        is_metadata_only=summary_row["is_metadata_only"],
        summary_version=summary_row["summary_version"],
    )
    return summary_row
