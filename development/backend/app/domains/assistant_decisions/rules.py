"""Command: create_rule_suggestion (job create_rule_suggestions) + approve —
assistant_decisions.md "Command: create_rule_suggestion".

Pattern extraction은 수정된 message에서 subject/sender만 읽고 raw body는 절대 읽지 않는다
("원본 메일 body는 참조 안 함" invariant).
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.outbox import append_event
from app.domains.assistant_decisions import events, repository

logger = structlog.get_logger()


def extract_condition(message: dict) -> dict | None:
    """subject/sender-only pattern extraction.

    usable signal이 없으면 None을 반환한다. caller는 empty-condition suggestion을 만들면
    안 된다(assistant_decisions.md "매칭 조건이 비었거나 패턴 추출 불가 → suggestion 미생성").
    """
    sender = (message.get("sender") or "").strip()
    if not sender:
        return None
    return {"sender": sender}


async def create_rule_suggestion_from_signal(
    connection: AsyncConnection, *, correction_signal_id: uuid.UUID
) -> dict | None:
    """insert된(또는 기존 pending) rule_suggestions row를 반환한다.

    pattern signal이 없어 suggestion을 만들지 않았으면 None을 반환한다.
    """
    signal = await repository.get_correction_signal(connection, signal_id=correction_signal_id)
    if signal is None:
        raise NotFoundError("correction signal not found")

    existing = await repository.get_pending_rule_suggestion_for_signal(
        connection, correction_signal_id=correction_signal_id
    )
    if existing is not None:
        # [멱등] 신호당 제안 하나 — 이미 있으면 중복 insert 안 함.
        return existing

    message = await repository.get_message(connection, message_id=signal["message_id"])
    if message is None:
        raise NotFoundError("message not found for correction signal")

    condition = extract_condition(message)
    if condition is None:
        logger.info(
            "패턴 추출 불가로 규칙 제안 생성 안 함",
            correction_signal_id=str(correction_signal_id),
        )
        return None

    label = await repository.get_service_label(
        connection, service_label_id=signal["service_label_id"]
    )
    if label is None:
        raise NotFoundError("service label not found for correction signal")

    suggestion_id = uuid.uuid4()
    await repository.insert_rule_suggestion(
        connection,
        suggestion_id=suggestion_id,
        workspace_id=label["workspace_id"],
        correction_signal_id=correction_signal_id,
        suggested_condition=condition,
    )
    await append_event(
        connection,
        event_type=events.RULE_SUGGESTION_CREATED,
        producer_domain="assistant_decisions",
        payload={
            "suggestion_id": str(suggestion_id),
            "correction_signal_id": str(correction_signal_id),
            "workspace_id": str(label["workspace_id"]),
        },
        idempotency_key=events.rule_suggestion_created_key(suggestion_id),
    )
    logger.info(
        "라벨 이동 신호로 규칙 제안 생성",
        correction_signal_id=str(correction_signal_id),
        suggestion_id=str(suggestion_id),
    )
    return await repository.get_rule_suggestion(connection, suggestion_id=suggestion_id)


async def approve_rule_suggestion(
    connection: AsyncConnection, *, suggestion_id: uuid.UUID, workspace_id: uuid.UUID
) -> dict:
    suggestion = await repository.get_rule_suggestion(connection, suggestion_id=suggestion_id)
    if suggestion is None:
        raise NotFoundError("rule suggestion not found")
    if suggestion["workspace_id"] != workspace_id:
        raise ForbiddenError("rule suggestion belongs to another workspace")

    if suggestion["status"] == "approved":
        # [멱등] 이미 approved면 no-op — 추가 classification_rules insert 없음.
        return suggestion
    if suggestion["status"] != "pending":
        raise ConflictError("only a pending rule suggestion can be approved")

    signal = await repository.get_correction_signal(
        connection, signal_id=suggestion["correction_signal_id"]
    )
    if signal is None:
        raise NotFoundError("correction signal not found for rule suggestion")

    now = datetime.now(timezone.utc)
    rule_id = uuid.uuid4()
    await repository.insert_classification_rule(
        connection,
        rule_id=rule_id,
        workspace_id=workspace_id,
        service_label_id=signal["service_label_id"],
        match_condition=suggestion["suggested_condition"],
    )
    await repository.mark_rule_suggestion_decided(
        connection, suggestion_id=suggestion_id, status="approved", decided_at=now
    )
    logger.info(
        "규칙 제안 승인",
        suggestion_id=str(suggestion_id),
        rule_id=str(rule_id),
    )
    return await repository.get_rule_suggestion(connection, suggestion_id=suggestion_id)


async def list_rules(connection: AsyncConnection, *, workspace_id: uuid.UUID) -> dict:
    suggestions = await repository.list_pending_rule_suggestions(
        connection, workspace_id=workspace_id
    )
    active_rules = await repository.list_active_classification_rules(
        connection, workspace_id=workspace_id
    )
    return {"suggestions": suggestions, "rules": active_rules}
