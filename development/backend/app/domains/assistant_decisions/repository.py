import uuid
from datetime import datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.assistant_decisions.models import (
    classification_rules,
    cleanup_proposals,
    importance_jobs,
    message_importance_classifications,
    message_summaries,
    rule_suggestions,
    summary_jobs,
)
from app.domains.labels.models import label_correction_signals, service_labels
from app.domains.mail_intake.models import gmail_message_labels, gmail_messages, message_excerpts
from app.domains.mail_sources.models import connected_gmail_accounts, gmail_source_settings

# ---- cross-domain read 조회 ------------------------------------------------
# assistant_decisions는 message/account/label data를 직접 소유하지 않는다. 아래 helper는
# 모두 다른 domain table에 대한 단순 read이며(labels.repository.get_connected_account_status와
# 같은 패턴), write는 절대 하지 않는다.


async def get_message(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(select(gmail_messages).where(gmail_messages.c.id == message_id))
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_message_workspace_and_account(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(
                connected_gmail_accounts.c.workspace_id,
                connected_gmail_accounts.c.id.label("connected_account_id"),
            )
            .select_from(gmail_messages)
            .join(
                connected_gmail_accounts,
                connected_gmail_accounts.c.id == gmail_messages.c.connected_account_id,
            )
            .where(gmail_messages.c.id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_message_labels(connection: AsyncConnection, *, message_id: uuid.UUID) -> list[str]:
    rows = (
        await connection.execute(
            select(gmail_message_labels.c.label_name).where(
                gmail_message_labels.c.message_id == message_id
            )
        )
    ).all()
    return [row[0] for row in rows]

async def get_message_excerpt(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> str | None:
    row = (
        await connection.execute(
            select(message_excerpts.c.excerpt_text).where(
                message_excerpts.c.message_id == message_id
            )
        )
    ).first()
    return row[0] if row is not None else None


async def get_summary_enabled(
    connection: AsyncConnection, *, connected_account_id: uuid.UUID
) -> bool:
    row = (
        await connection.execute(
            select(gmail_source_settings.c.summary_enabled).where(
                gmail_source_settings.c.connected_account_id == connected_account_id
            )
        )
    ).first()
    # 아직 settings row가 없으면 default-on으로 취급한다(mail_sources의
    # 0003_mail_sources migration에 있는 column server_default="true"와 일치).
    return True if row is None else bool(row[0])


async def get_correction_signal(
    connection: AsyncConnection, *, signal_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(label_correction_signals).where(label_correction_signals.c.id == signal_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def get_service_label(
    connection: AsyncConnection, *, service_label_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(service_labels).where(service_labels.c.id == service_label_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


# ---- summary_jobs / message_summaries 관리 ---------------------------------


async def insert_summary_job(
    connection: AsyncConnection, *, job_id: uuid.UUID, message_id: uuid.UUID, created_at: datetime
) -> None:
    await connection.execute(
        insert(summary_jobs).values(
            id=job_id,
            message_id=message_id,
            status="queued",
            attempt_count=0,
            created_at=created_at,
        )
    )


async def mark_summary_job_running(connection: AsyncConnection, *, job_id: uuid.UUID) -> None:
    await connection.execute(
        update(summary_jobs).where(summary_jobs.c.id == job_id).values(status="running")
    )


async def mark_summary_job_succeeded(
    connection: AsyncConnection, *, job_id: uuid.UUID, finished_at: datetime
) -> None:
    await connection.execute(
        update(summary_jobs)
        .where(summary_jobs.c.id == job_id)
        .values(status="succeeded", finished_at=finished_at)
    )


async def mark_summary_job_failed(
    connection: AsyncConnection, *, job_id: uuid.UUID, finished_at: datetime
) -> None:
    await connection.execute(
        update(summary_jobs)
        .where(summary_jobs.c.id == job_id)
        .values(
            status="failed",
            finished_at=finished_at,
            attempt_count=summary_jobs.c.attempt_count + 1,
        )
    )


async def get_message_summary(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(message_summaries).where(message_summaries.c.message_id == message_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def upsert_message_summary(
    connection: AsyncConnection,
    *,
    message_id: uuid.UUID,
    summary_text: str | None,
    is_metadata_only: bool,
    model_name: str | None,
) -> dict:
    existing = await get_message_summary(connection, message_id=message_id)
    if existing is None:
        summary_id = uuid.uuid4()
        await connection.execute(
            insert(message_summaries).values(
                id=summary_id,
                message_id=message_id,
                summary_text=summary_text,
                is_metadata_only=is_metadata_only,
                summary_version=1,
                model_name=model_name,
            )
        )
        return await get_message_summary(connection, message_id=message_id)

    new_version = existing["summary_version"] + 1
    await connection.execute(
        update(message_summaries)
        .where(message_summaries.c.message_id == message_id)
        .values(
            summary_text=summary_text,
            is_metadata_only=is_metadata_only,
            summary_version=new_version,
            model_name=model_name,
        )
    )
    return await get_message_summary(connection, message_id=message_id)


# ---- importance_jobs / message_importance_classifications 관리 --------------


async def insert_importance_job(
    connection: AsyncConnection, *, job_id: uuid.UUID, message_id: uuid.UUID, created_at: datetime
) -> None:
    await connection.execute(
        insert(importance_jobs).values(
            id=job_id,
            message_id=message_id,
            status="queued",
            attempt_count=0,
            created_at=created_at,
        )
    )


async def mark_importance_job_running(connection: AsyncConnection, *, job_id: uuid.UUID) -> None:
    await connection.execute(
        update(importance_jobs).where(importance_jobs.c.id == job_id).values(status="running")
    )


async def mark_importance_job_succeeded(
    connection: AsyncConnection, *, job_id: uuid.UUID, finished_at: datetime
) -> None:
    await connection.execute(
        update(importance_jobs)
        .where(importance_jobs.c.id == job_id)
        .values(status="succeeded", finished_at=finished_at)
    )


async def mark_importance_job_failed(
    connection: AsyncConnection, *, job_id: uuid.UUID, finished_at: datetime
) -> None:
    await connection.execute(
        update(importance_jobs)
        .where(importance_jobs.c.id == job_id)
        .values(
            status="failed",
            finished_at=finished_at,
            attempt_count=importance_jobs.c.attempt_count + 1,
        )
    )


async def get_message_importance_classification(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(message_importance_classifications).where(
                message_importance_classifications.c.message_id == message_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def upsert_message_importance_classification(
    connection: AsyncConnection,
    *,
    message_id: uuid.UUID,
    importance_band: str,
    reason: str,
) -> dict:
    existing = await get_message_importance_classification(connection, message_id=message_id)
    if existing is None:
        row_id = uuid.uuid4()
        await connection.execute(
            insert(message_importance_classifications).values(
                id=row_id,
                message_id=message_id,
                importance_band=importance_band,
                reason=reason,
                classification_version=1,
            )
        )
        return await get_message_importance_classification(connection, message_id=message_id)

    new_version = existing["classification_version"] + 1
    await connection.execute(
        update(message_importance_classifications)
        .where(message_importance_classifications.c.message_id == message_id)
        .values(importance_band=importance_band, reason=reason, classification_version=new_version)
    )
    return await get_message_importance_classification(connection, message_id=message_id)


# ---- classification_rules / rule_suggestions 관리 ---------------------------


async def get_pending_rule_suggestion_for_signal(
    connection: AsyncConnection, *, correction_signal_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(rule_suggestions).where(
                rule_suggestions.c.correction_signal_id == correction_signal_id
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def insert_rule_suggestion(
    connection: AsyncConnection,
    *,
    suggestion_id: uuid.UUID,
    workspace_id: uuid.UUID,
    correction_signal_id: uuid.UUID,
    suggested_condition: dict,
) -> None:
    await connection.execute(
        insert(rule_suggestions).values(
            id=suggestion_id,
            workspace_id=workspace_id,
            correction_signal_id=correction_signal_id,
            suggested_condition=suggested_condition,
            status="pending",
            decided_at=None,
        )
    )


async def get_rule_suggestion(
    connection: AsyncConnection, *, suggestion_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(rule_suggestions).where(rule_suggestions.c.id == suggestion_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def mark_rule_suggestion_decided(
    connection: AsyncConnection,
    *,
    suggestion_id: uuid.UUID,
    status: str,
    decided_at: datetime,
) -> None:
    await connection.execute(
        update(rule_suggestions)
        .where(rule_suggestions.c.id == suggestion_id)
        .values(status=status, decided_at=decided_at)
    )


async def list_pending_rule_suggestions(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[dict]:
    rows = (
        await connection.execute(
            select(rule_suggestions).where(
                rule_suggestions.c.workspace_id == workspace_id,
                rule_suggestions.c.status == "pending",
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def insert_classification_rule(
    connection: AsyncConnection,
    *,
    rule_id: uuid.UUID,
    workspace_id: uuid.UUID,
    service_label_id: uuid.UUID,
    match_condition: dict,
) -> None:
    await connection.execute(
        insert(classification_rules).values(
            id=rule_id,
            workspace_id=workspace_id,
            service_label_id=service_label_id,
            match_condition=match_condition,
            active=True,
        )
    )


async def list_active_classification_rules(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[dict]:
    rows = (
        await connection.execute(
            select(classification_rules).where(
                classification_rules.c.workspace_id == workspace_id,
                classification_rules.c.active.is_(True),
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]


# ---- cleanup_proposals 관리 -------------------------------------------------


async def get_pending_cleanup_proposal_for_message_action(
    connection: AsyncConnection, *, message_id: uuid.UUID, proposed_action: str
) -> dict | None:
    row = (
        await connection.execute(
            select(cleanup_proposals).where(
                cleanup_proposals.c.message_id == message_id,
                cleanup_proposals.c.proposed_action == proposed_action,
                cleanup_proposals.c.status == "pending",
            )
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def count_cleanup_proposals_for_message(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> int:
    count = (
        await connection.execute(
            select(func.count())
            .select_from(cleanup_proposals)
            .where(cleanup_proposals.c.message_id == message_id)
        )
    ).scalar()
    return count or 0


async def insert_cleanup_proposal(
    connection: AsyncConnection,
    *,
    proposal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    proposed_action: str,
    confidence_band: str,
    status: str,
    before_state: dict,
    after_state: dict | None,
    gmail_action_command_id: uuid.UUID | None,
    decided_at: datetime | None,
) -> None:
    await connection.execute(
        insert(cleanup_proposals).values(
            id=proposal_id,
            workspace_id=workspace_id,
            message_id=message_id,
            proposed_action=proposed_action,
            confidence_band=confidence_band,
            status=status,
            before_state=before_state,
            after_state=after_state,
            gmail_action_command_id=gmail_action_command_id,
            decided_at=decided_at,
        )
    )


async def get_cleanup_proposal(
    connection: AsyncConnection, *, proposal_id: uuid.UUID
) -> dict | None:
    row = (
        await connection.execute(
            select(cleanup_proposals).where(cleanup_proposals.c.id == proposal_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def mark_cleanup_proposal_decided(
    connection: AsyncConnection,
    *,
    proposal_id: uuid.UUID,
    status: str,
    decided_at: datetime,
    gmail_action_command_id: uuid.UUID | None,
) -> None:
    await connection.execute(
        update(cleanup_proposals)
        .where(cleanup_proposals.c.id == proposal_id)
        .values(status=status, decided_at=decided_at, gmail_action_command_id=gmail_action_command_id)
    )


async def list_cleanup_review_queue(
    connection: AsyncConnection, *, workspace_id: uuid.UUID
) -> list[dict]:
    """approval-required band + pending status만 포함한다.

    approve-one-only review queue다(assistant_decisions.md "GET /cleanup").
    """
    from app.domains.assistant_decisions.fake_llm import FAKE_CONFIDENCE_APPROVAL_REQUIRED

    rows = (
        await connection.execute(
            select(cleanup_proposals).where(
                cleanup_proposals.c.workspace_id == workspace_id,
                cleanup_proposals.c.status == "pending",
                cleanup_proposals.c.confidence_band == FAKE_CONFIDENCE_APPROVAL_REQUIRED,
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows]
