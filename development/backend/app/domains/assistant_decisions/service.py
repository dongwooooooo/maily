"""Shared read-context helpers used by summaries.py, importance.py, and
cleanup.py — message lookup + LLM payload assembly. Centralized here so
the "never pass raw body/prompt" boundary is enforced in exactly one place
(module-boundaries.md "LLM payload는 최소만") instead of duplicated per job.
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
    """Returns {"workspace_id", "connected_account_id"} for a message —
    raises NotFoundError if the message has no snapshot (assistant_decisions
    never evaluates a message that doesn't exist per mail_intake)."""
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
