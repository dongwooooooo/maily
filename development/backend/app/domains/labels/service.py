import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import idempotency
from app.core.errors import ForbiddenError, MailyError, NotFoundError, ValidationError
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action
from app.domains.labels import repository
from app.domains.labels.events import record_label_correction_recorded
from app.domains.labels.schemas import (
    CreateLabelInput,
    MoveMessageInput,
    MoveMessageResult,
    ServiceLabel,
    UpdateLabelInput,
)

_INACTIVE_ACCOUNT_STATUSES = ("disconnected", "disconnecting")
_MOVE_IDEMPOTENCY_SCOPE = "labels.move_message_to_label"
_MOVE_IDEMPOTENCY_TTL = timedelta(hours=24)

logger = structlog.get_logger()


def _to_schema(label: dict, mapping: dict) -> ServiceLabel:
    return ServiceLabel(
        id=label["id"],
        workspace_id=label["workspace_id"],
        name=label["name"],
        order_index=label["order_index"],
        hidden=label["hidden"],
        updated_at=label["updated_at"],
        connected_account_id=mapping["connected_account_id"],
        gmail_label_id=mapping["gmail_label_id"],
        gmail_label_name=mapping["gmail_label_name"],
    )


async def create_or_update_label(
    connection: AsyncConnection, data: CreateLabelInput
) -> tuple[ServiceLabel, bool]:
    """Create a user label plus its Gmail mapping intent.

    Idempotent on (workspace_id, name): a sequential duplicate is caught
    by the pre-check below and returns the existing label with is_new
    False (no second mapping row created); a genuinely concurrent
    duplicate is caught by the UNIQUE(workspace_id, name) constraint and
    falls back to the same re-query.

    Does not create or reconcile the Gmail-side `Maily` parent label —
    that is gmail_actions' job at actual apply time (labels never calls
    Gmail directly). See the "resolved ambiguity" note in the task
    report for why this domain does not track a parent-label row.
    """
    name = data.name.strip()
    if not name:
        raise ValidationError("label name must not be blank")

    status = await repository.get_connected_account_status(
        connection, connected_account_id=data.connected_account_id
    )
    if status is None or status in _INACTIVE_ACCOUNT_STATUSES:
        raise ValidationError("connected account is not active")

    existing = await repository.get_service_label_by_name(
        connection, workspace_id=data.workspace_id, name=name
    )
    if existing is not None:
        mapping = await repository.get_gmail_label_mapping(
            connection, service_label_id=existing["id"]
        )
        return _to_schema(existing, mapping), False

    label_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    order_index = (
        data.order_index
        if data.order_index is not None
        else await repository.next_order_index(connection, workspace_id=data.workspace_id)
    )

    try:
        async with connection.begin_nested():
            await repository.insert_service_label(
                connection,
                label_id=label_id,
                workspace_id=data.workspace_id,
                name=name,
                order_index=order_index,
                hidden=data.hidden,
                updated_at=now,
            )
    except IntegrityError:
        existing = await repository.get_service_label_by_name(
            connection, workspace_id=data.workspace_id, name=name
        )
        if existing is None:
            raise
        mapping = await repository.get_gmail_label_mapping(
            connection, service_label_id=existing["id"]
        )
        return _to_schema(existing, mapping), False

    mapping_id = uuid.uuid4()
    gmail_label_name = f"Maily/{name}"
    await repository.insert_gmail_label_mapping(
        connection,
        mapping_id=mapping_id,
        service_label_id=label_id,
        connected_account_id=data.connected_account_id,
        gmail_label_name=gmail_label_name,
    )

    label_row = {
        "id": label_id,
        "workspace_id": data.workspace_id,
        "name": name,
        "order_index": order_index,
        "hidden": data.hidden,
        "updated_at": now,
    }
    mapping_row = {
        "connected_account_id": data.connected_account_id,
        "gmail_label_id": None,
        "gmail_label_name": gmail_label_name,
    }
    logger.info("사용자 라벨 생성", label_id=str(label_id), gmail_label_name=gmail_label_name)
    return _to_schema(label_row, mapping_row), True


async def get_owned_label(
    connection: AsyncConnection, *, label_id: uuid.UUID, workspace_id: uuid.UUID
) -> dict:
    label = await repository.get_service_label(connection, label_id=label_id)
    if label is None:
        raise NotFoundError("label not found")
    if label["workspace_id"] != workspace_id:
        raise ForbiddenError("label belongs to another workspace")
    return label


async def update_label(
    connection: AsyncConnection, *, label_id: uuid.UUID, changes: UpdateLabelInput
) -> ServiceLabel:
    """Apply a partial rename/reorder/hide update.

    Never creates a second gmail_label_mappings row — rename only
    updates service_labels.name and the existing mapping's
    gmail_label_name; the Gmail-side gmail_label_id (once set by
    gmail_actions) is left untouched. A no-op update (merged values
    equal current values) skips the updated_at bump entirely.
    """
    label = await repository.get_service_label(connection, label_id=label_id)
    if label is None:
        raise NotFoundError("label not found")

    provided = changes.model_dump(exclude_unset=True)
    new_name = provided.get("name", label["name"])
    if "name" in provided and not new_name.strip():
        raise ValidationError("label name must not be blank")
    new_name = new_name.strip() if "name" in provided else new_name
    new_order_index = provided.get("order_index", label["order_index"])
    new_hidden = provided.get("hidden", label["hidden"])

    mapping = await repository.get_gmail_label_mapping(connection, service_label_id=label_id)

    changed = (
        new_name != label["name"]
        or new_order_index != label["order_index"]
        or new_hidden != label["hidden"]
    )
    if not changed:
        return _to_schema(label, mapping)

    now = datetime.now(timezone.utc)
    await repository.update_service_label(
        connection,
        label_id=label_id,
        name=new_name,
        order_index=new_order_index,
        hidden=new_hidden,
        updated_at=now,
    )

    new_gmail_label_name = mapping["gmail_label_name"]
    if new_name != label["name"]:
        new_gmail_label_name = f"Maily/{new_name}"
        await repository.update_gmail_label_mapping_name(
            connection, service_label_id=label_id, gmail_label_name=new_gmail_label_name
        )

    updated_label = {
        **label,
        "name": new_name,
        "order_index": new_order_index,
        "hidden": new_hidden,
        "updated_at": now,
    }
    updated_mapping = {**mapping, "gmail_label_name": new_gmail_label_name}
    return _to_schema(updated_label, updated_mapping)


async def list_labels(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, include_hidden: bool
) -> list[ServiceLabel]:
    labels = await repository.list_service_labels(
        connection, workspace_id=workspace_id, include_hidden=include_hidden
    )
    result = []
    for label in labels:
        mapping = await repository.get_gmail_label_mapping(
            connection, service_label_id=label["id"]
        )
        result.append(_to_schema(label, mapping))
    return result


async def move_message_to_label(
    connection: AsyncConnection, data: MoveMessageInput
) -> MoveMessageResult:
    """Record a correction signal for a user-triggered move, emit
    label_correction_recorded, and request the Gmail label apply command.

    labels.md §정상/§경계: labels never imports GmailMutationPort or calls
    Gmail directly — it requests the mutation via gmail_actions.
    request_gmail_action (IC5, docs/goals/backend-plans/_build-schedule.md).
    This is a direct synchronous call, not event/dispatcher-wired — labels.md
    §73 is explicit that _integration-contract.md §3 has no
    label_correction_recorded -> gmail_actions row (deliberate: the event
    is for create_rule_suggestions only). request_gmail_action's own
    idempotency (a distinct key, derived from this signal) means a retry
    of this whole function after a partial failure can't double-apply.
    """
    is_new_key = await idempotency.reserve(
        connection,
        scope=_MOVE_IDEMPOTENCY_SCOPE,
        key=data.idempotency_key,
        expires_at=datetime.now(timezone.utc) + _MOVE_IDEMPOTENCY_TTL,
    )
    if not is_new_key:
        cached = await idempotency.get_response(
            connection, scope=_MOVE_IDEMPOTENCY_SCOPE, key=data.idempotency_key
        )
        if cached is not None:
            return MoveMessageResult(**cached)

    message_workspace = await repository.get_message_workspace(
        connection, message_id=data.message_id
    )
    if message_workspace is None:
        raise NotFoundError("message not found")
    if message_workspace != data.workspace_id:
        raise ForbiddenError("message belongs to another workspace")

    label = await repository.get_service_label(connection, label_id=data.label_id)
    if label is None or label["workspace_id"] != data.workspace_id:
        # Move targets must be one of the caller's own service_labels —
        # never a default briefing section (there is no such
        # table/concept in this domain to move to).
        raise ValidationError("move target must be a user label in this workspace")

    mapping = await repository.get_gmail_label_mapping(
        connection, service_label_id=data.label_id
    )
    account_status = await repository.get_connected_account_status(
        connection, connected_account_id=mapping["connected_account_id"]
    )
    if account_status in _INACTIVE_ACCOUNT_STATUSES:
        raise ValidationError("label belongs to a disconnected account")

    version = await repository.count_label_correction_signals(
        connection, message_id=data.message_id, service_label_id=data.label_id
    )
    signal_id = uuid.uuid4()
    await repository.insert_label_correction_signal(
        connection,
        signal_id=signal_id,
        message_id=data.message_id,
        service_label_id=data.label_id,
        actor_id=data.actor_id,
    )
    await record_label_correction_recorded(
        connection,
        signal_id=signal_id,
        message_id=data.message_id,
        service_label_id=data.label_id,
        version=version,
    )

    # gmail_label_id is null until gmail_actions has actually created the
    # label in Gmail (models.py "매핑 분리 근거") — label create/rename as
    # its own gmail_actions action_type is out of this IC's scope, so this
    # falls back to gmail_label_name (e.g. "Maily/업무") as the mutation
    # target, which the fake mutator (and this POC's action vocabulary)
    # treats as an opaque label identifier either way.
    #
    # labels.md §61 documents the correction signal as independently
    # durable ("signal 커밋 후 프로세스 사망해도 재기동 시 재요청") — this
    # call shares the router's one transaction with the signal insert
    # above, so a request_gmail_action failure must not abort that
    # transaction and discard an already-recorded signal. request_gmail_
    # action's own guard-clause raises (unsupported action_type, account
    # not found/wrong workspace, account disconnecting — all reads, no
    # writes before the raise) are caught here for exactly that reason;
    # anything else (a genuine bug) still propagates.
    try:
        await request_gmail_action(
            connection,
            RequestGmailActionInput(
                workspace_id=data.workspace_id,
                connected_account_id=mapping["connected_account_id"],
                message_id=data.message_id,
                action_type="label_apply",
                gmail_label_id=mapping["gmail_label_id"] or mapping["gmail_label_name"],
                idempotency_key=f"label-apply:{signal_id}",
                requested_by=data.actor_id,
            ),
        )
    except MailyError as exc:
        logger.warning(
            "라벨 이동 신호는 기록됐지만 Gmail 적용 커맨드 요청 실패 — signal은 유지",
            signal_id=str(signal_id),
            message_id=str(data.message_id),
            reason=str(exc),
        )

    result = MoveMessageResult(
        correction_signal_id=signal_id,
        message_id=data.message_id,
        service_label_id=data.label_id,
        version=version,
    )
    await idempotency.store_response(
        connection,
        scope=_MOVE_IDEMPOTENCY_SCOPE,
        key=data.idempotency_key,
        response_snapshot=result.model_dump(mode="json"),
    )
    logger.info(
        "메일 라벨 이동 신호 기록",
        message_id=str(data.message_id),
        service_label_id=str(data.label_id),
    )
    return result
