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
    """user label과 Gmail mapping intent를 생성한다.

    (workspace_id, name)에 대해 idempotent하다. sequential duplicate는 아래 pre-check에 잡혀
    기존 label과 is_new False를 반환한다(두 번째 mapping row 생성 없음). 실제 concurrent
    duplicate는 UNIQUE(workspace_id, name) constraint에 잡히고 같은 re-query로 fallback한다.

    Gmail-side `Maily` parent label을 생성하거나 reconcile하지 않는다. 이는 실제 apply 시점의
    gmail_actions job이다(labels는 Gmail을 직접 호출하지 않음). 이 domain이 parent-label row를
    추적하지 않는 이유는 task report의 "resolved ambiguity" note 참고.
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
    """부분 rename/reorder/hide update를 적용한다.

    두 번째 gmail_label_mappings row는 절대 만들지 않는다. rename은 service_labels.name과 기존
    mapping의 gmail_label_name만 update한다. Gmail-side gmail_label_id(gmail_actions가 한 번
    설정하면)는 건드리지 않는다. no-op update(merged value가 current value와 같음)는
    updated_at bump도 완전히 건너뛴다.
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
    """user-triggered move의 correction signal을 기록하고 label_correction_recorded를 emit한 뒤
    Gmail label apply command를 요청한다.

    labels.md §정상/§경계: labels는 GmailMutationPort를 import하거나 Gmail을 직접 호출하지 않는다.
    gmail_actions.request_gmail_action을 통해 mutation을 요청한다(IC5,
    docs/goals/backend-plans/_build-schedule.md). 이는 event/dispatcher-wired가 아니라 direct
    synchronous call이다. labels.md §73은 _integration-contract.md §3에
    label_correction_recorded -> gmail_actions row가 없다고 명시한다(의도적: event는
    create_rule_suggestions 전용). request_gmail_action 자체 idempotency(이 signal에서 파생한
    별도 key) 덕분에 partial failure 이후 이 전체 function이 retry되어도 double-apply되지 않는다.
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
        # move target은 caller 자신의 service_labels 중 하나여야 한다. default briefing section은
        # 안 된다(이 domain에는 이동 대상이 될 그런 table/concept가 없음).
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

    # gmail_label_id는 gmail_actions가 Gmail에 실제 label을 만들 때까지 null이다(models.py
    # "매핑 분리 근거"). 자체 gmail_actions action_type으로서 label create/rename은 이 IC 범위
    # 밖이므로, mutation target으로 gmail_label_name(예: "Maily/업무")에 fallback한다.
    # fake mutator와 이 POC의 action vocabulary는 어느 쪽이든 이를 opaque label identifier로 취급한다.
    #
    # labels.md §61은 correction signal이 독립적으로 durable하다고 문서화한다
    # ("signal 커밋 후 프로세스 사망해도 재기동 시 재요청"). 이 call은 위 signal insert와 router의
    # 단일 transaction을 공유하므로, request_gmail_action failure가 그 transaction을 abort해 이미
    # 기록된 signal을 버리면 안 된다. request_gmail_action 자체 guard-clause raise(unsupported
    # action_type, account not found/wrong workspace, account disconnecting — 모두 raise 전 read만
    # 있고 write 없음)는 정확히 그 이유로 여기서 catch한다. 그 밖의 진짜 bug는 계속 propagate한다.
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
