import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.outbox import append_event
from app.domains.gmail_actions import events, repository
from app.domains.gmail_actions.schemas import (
    SUPPORTED_ACTION_TYPES,
    GmailActionCommand,
    RequestGmailActionInput,
)


def build_action_payload(action_type: str, *, gmail_label_id: str | None) -> dict:
    """action_type -> uniform {add_label_ids, remove_label_ids} payload.

    docs/goals/backend-plans/gmail_actions.md "Command: request_gmail_action" —
    one payload shape for every action_type, never a per-type shape.
    """
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise ValidationError(f"unsupported action_type: {action_type}")
    if action_type == "mark_read":
        return {"add_label_ids": [], "remove_label_ids": ["UNREAD"]}
    if action_type == "archive":
        return {"add_label_ids": [], "remove_label_ids": ["INBOX"]}
    if action_type == "read_and_archive":
        return {"add_label_ids": [], "remove_label_ids": ["UNREAD", "INBOX"]}
    # label_apply
    if not gmail_label_id:
        raise ValidationError("label_apply requires gmail_label_id")
    return {"add_label_ids": [gmail_label_id], "remove_label_ids": []}


def _to_schema(row: dict) -> GmailActionCommand:
    return GmailActionCommand(**row)


async def request_gmail_action(
    connection: AsyncConnection, data: RequestGmailActionInput
) -> tuple[GmailActionCommand, bool]:
    """[정상]/[멱등]/[동시]/[선행조건]/[부분실패] — see gmail_actions.md.

    Only ever creates a `pending` command + `gmail_action_requested` event in
    the same transaction as the caller's connection — no Gmail call happens
    here (that's execute_action's job). Idempotent on the client-supplied
    `idempotency_key`: a retried request (sequential or racing) returns the
    original command with is_new=False instead of a second row/event.
    """
    existing = await repository.get_command_by_idempotency_key(
        connection, idempotency_key=data.idempotency_key
    )
    if existing is not None:
        return _to_schema(existing), False

    if data.action_type not in SUPPORTED_ACTION_TYPES:
        raise ValidationError(f"unsupported action_type: {data.action_type}")

    scope = await repository.get_connected_account_scope(
        connection, connected_account_id=data.connected_account_id
    )
    if scope is None or scope["workspace_id"] != data.workspace_id:
        # 404 either way — existence of another workspace's account is not revealed.
        raise NotFoundError("gmail source not found")
    if scope["status"] in ("disconnecting", "disconnected"):
        raise ConflictError("gmail source is disconnecting or disconnected")

    payload = build_action_payload(data.action_type, gmail_label_id=data.gmail_label_id)
    command_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    try:
        async with connection.begin_nested():
            await repository.insert_command(
                connection,
                command_id=command_id,
                connected_account_id=data.connected_account_id,
                message_id=data.message_id,
                action_type=data.action_type,
                payload=payload,
                idempotency_key=data.idempotency_key,
                requested_by=data.requested_by,
                requested_at=now,
            )
    except IntegrityError:
        existing = await repository.get_command_by_idempotency_key(
            connection, idempotency_key=data.idempotency_key
        )
        if existing is None:
            raise
        return _to_schema(existing), False

    await append_event(
        connection,
        event_type=events.GMAIL_ACTION_REQUESTED,
        producer_domain="gmail_actions",
        payload={"command_id": str(command_id)},
        idempotency_key=events.requested_key(command_id),
    )

    command = await repository.get_command(connection, command_id=command_id)
    return _to_schema(command), True


async def get_command_for_workspace(
    connection: AsyncConnection, *, command_id: uuid.UUID, workspace_id: uuid.UUID
) -> GmailActionCommand:
    command = await repository.get_command(connection, command_id=command_id)
    if command is None:
        raise NotFoundError("gmail action command not found")
    scope = await repository.get_connected_account_scope(
        connection, connected_account_id=command["connected_account_id"]
    )
    if scope is None or scope["workspace_id"] != workspace_id:
        raise NotFoundError("gmail action command not found")
    return _to_schema(command)
