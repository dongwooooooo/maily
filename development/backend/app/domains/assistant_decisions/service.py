"""summaries.py, importance.py, cleanup.py가 공유하는 read-context helper.

message lookup + LLM payload assembly를 담당한다. job마다 중복하지 않고 여기에서
centralize해 "never pass raw body/prompt" boundary를 정확히 한 곳에서 강제한다
(module-boundaries.md "LLM payload는 최소만").
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import NotFoundError
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.llm import CleanupSignal, ImportanceInput, SummaryInput


async def get_message_or_404(connection: AsyncConnection, *, message_id: uuid.UUID) -> dict:
    message = await repository.get_message(connection, message_id=message_id)
    if message is None:
        raise NotFoundError("message snapshot not found")
    return message


async def resolve_message_scope_or_404(
    connection: AsyncConnection, *, message_id: uuid.UUID
) -> dict:
    """message의 {"workspace_id", "connected_account_id"}를 반환한다.

    message에 snapshot이 없으면 NotFoundError를 raise한다(assistant_decisions는 mail_intake
    기준 존재하지 않는 message를 평가하지 않는다).
    """
    scope = await repository.get_message_workspace_and_account(connection, message_id=message_id)
    if scope is None:
        raise NotFoundError("message snapshot not found")
    return scope


async def build_summary_payload(
    connection: AsyncConnection, *, message: dict
) -> SummaryInput:
    labels = await repository.get_message_labels(connection, message_id=message["id"])
    excerpt = await repository.get_message_excerpt(connection, message_id=message["id"])
    return SummaryInput(
        subject=message.get("subject"),
        sender=message.get("sender"),
        snippet=message.get("snippet"),
        labels=labels,
        excerpt=excerpt,
    )


async def build_importance_payload(
    connection: AsyncConnection, *, message: dict
) -> ImportanceInput:
    labels = await repository.get_message_labels(connection, message_id=message["id"])
    return ImportanceInput(
        subject=message.get("subject"),
        sender=message.get("sender"),
        snippet=message.get("snippet"),
        labels=labels,
        is_read=bool(message.get("is_read", False)),
    )


async def build_cleanup_signal(connection: AsyncConnection, *, message: dict) -> CleanupSignal:
    labels = await repository.get_message_labels(connection, message_id=message["id"])
    return CleanupSignal(
        is_read=bool(message.get("is_read", False)),
        is_archived=bool(message.get("is_archived", False)),
        label_names=labels,
    )
