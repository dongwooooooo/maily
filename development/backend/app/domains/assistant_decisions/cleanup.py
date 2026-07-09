"""Job: prepare_cleanup_proposals + Command: approve_cleanup_proposal —
assistant_decisions.md "Job: prepare_cleanup_proposals" / "Command:
approve_cleanup_proposal".

Deviation note (see task report): F10/module-boundaries.md explicitly say
assistant_decisions "승인 후 gmail_actions command를 요청할 수 있다" — the
sanctioned way to do that without calling Gmail directly is gmail_actions'
own public `request_gmail_action` (it only inserts a pending command +
emits gmail_action_requested; no Gmail call happens inside it either).
gmail_actions is already merged in this worktree, so this module imports
it directly for the approve/auto-apply path rather than duplicating its
idempotency-safe insert logic. This is the one place this domain reaches
into another domain's service layer.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.outbox import append_event
from app.domains.assistant_decisions import events, repository, service
from app.domains.assistant_decisions.fake_llm import FAKE_CONFIDENCE_AUTO_APPLY
from app.domains.assistant_decisions.llm import get_llm
from app.domains.gmail_actions.schemas import RequestGmailActionInput
from app.domains.gmail_actions.service import request_gmail_action

logger = structlog.get_logger()


def _before_after_state(message: dict, labels: list[str], *, proposed_action: str) -> tuple[dict, dict]:
    before_state = {
        "is_read": message.get("is_read", False),
        "is_archived": message.get("is_archived", False),
        "labels": sorted(labels),
    }
    after_labels = set(labels)
    after_is_read = message.get("is_read", False)
    after_is_archived = message.get("is_archived", False)
    if proposed_action in ("archive", "read_and_archive"):
        after_labels.discard("INBOX")
        after_is_archived = True
    if proposed_action in ("mark_read", "read_and_archive"):
        after_labels.discard("UNREAD")
        after_is_read = True
    after_state = {
        "is_read": after_is_read,
        "is_archived": after_is_archived,
        "labels": sorted(after_labels),
    }
    return before_state, after_state


async def _request_gmail_command_for_proposal(
    connection: AsyncConnection,
    *,
    proposal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    proposed_action: str,
    requested_by: uuid.UUID,
):
    scope = await service.resolve_message_scope_or_404(connection, message_id=message_id)
    data = RequestGmailActionInput(
        workspace_id=workspace_id,
        connected_account_id=scope["connected_account_id"],
        message_id=message_id,
        action_type=proposed_action,
        idempotency_key=f"cleanup:{proposal_id}:apply",
        requested_by=requested_by,
    )
    command, _ = await request_gmail_action(connection, data)
    return command


async def prepare_cleanup_proposals(
    connection: AsyncConnection,
    *,
    workspace_id: uuid.UUID,
    message_ids: list[uuid.UUID],
    requested_by: uuid.UUID,
) -> list[dict]:
    """payload={workspace_id, message_ids} — this worktree always requires
    explicit message_ids (the "scan the whole workspace" enumeration path
    is out of scope for this fake/POC pass; see task report open question).
    `requested_by` is only used for the auto-apply immediate command
    request (assistant acting as the requester of record)."""
    created: list[dict] = []
    for message_id in message_ids:
        scope = await service.resolve_message_scope_or_404(connection, message_id=message_id)
        if scope["workspace_id"] != workspace_id:
            raise ForbiddenError("message belongs to another workspace")

        message = await service.get_message_or_404(connection, message_id=message_id)
        signal = await service.build_cleanup_signal(connection, message=message)
        assessment = get_llm().assess_cleanup(signal)

        if assessment["confidence_band"] == "silent" or assessment["proposed_action"] is None:
            continue

        proposed_action = assessment["proposed_action"]
        existing = await repository.get_pending_cleanup_proposal_for_message_action(
            connection, message_id=message_id, proposed_action=proposed_action
        )
        if existing is not None:
            # [멱등] 같은 후보 중복 proposal 방지(message+action 기준 pending 하나).
            created.append(existing)
            continue

        before_state, after_state = _before_after_state(
            message, signal["label_names"], proposed_action=proposed_action
        )
        proposal_id = uuid.uuid4()
        proposal_version = (
            await repository.count_cleanup_proposals_for_message(connection, message_id=message_id)
        ) + 1

        status = "pending"
        decided_at = None
        gmail_action_command_id = None
        if assessment["confidence_band"] == FAKE_CONFIDENCE_AUTO_APPLY:
            command = await _request_gmail_command_for_proposal(
                connection,
                proposal_id=proposal_id,
                workspace_id=workspace_id,
                message_id=message_id,
                proposed_action=proposed_action,
                requested_by=requested_by,
            )
            status = "approved"
            decided_at = datetime.now(timezone.utc)
            gmail_action_command_id = command.id

        await repository.insert_cleanup_proposal(
            connection,
            proposal_id=proposal_id,
            workspace_id=workspace_id,
            message_id=message_id,
            proposed_action=proposed_action,
            confidence_band=assessment["confidence_band"],
            status=status,
            before_state=before_state,
            after_state=after_state,
            gmail_action_command_id=gmail_action_command_id,
            decided_at=decided_at,
        )
        await append_event(
            connection,
            event_type=events.CLEANUP_PROPOSAL_CREATED,
            producer_domain="assistant_decisions",
            payload={
                "proposal_id": str(proposal_id),
                "workspace_id": str(workspace_id),
                "message_id": str(message_id),
                "proposal_version": proposal_version,
                "confidence_band": assessment["confidence_band"],
                "proposed_action": proposed_action,
            },
            idempotency_key=events.cleanup_proposal_created_key(message_id, proposal_version),
        )
        logger.info(
            "정리 제안 생성",
            message_id=str(message_id),
            confidence_band=assessment["confidence_band"],
            proposed_action=proposed_action,
        )
        created.append(await repository.get_cleanup_proposal(connection, proposal_id=proposal_id))

    return created


async def approve_cleanup_proposal(
    connection: AsyncConnection,
    *,
    proposal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict:
    proposal = await repository.get_cleanup_proposal(connection, proposal_id=proposal_id)
    if proposal is None:
        raise NotFoundError("cleanup proposal not found")
    if proposal["workspace_id"] != workspace_id:
        raise ForbiddenError("cleanup proposal belongs to another workspace")

    if proposal["status"] in ("approved", "applied"):
        # [멱등] 이미 approved/applied면 no-op — 추가 command 요청 없음.
        return proposal
    if proposal["status"] != "pending":
        raise ConflictError("only a pending cleanup proposal can be approved")

    command = await _request_gmail_command_for_proposal(
        connection,
        proposal_id=proposal_id,
        workspace_id=workspace_id,
        message_id=proposal["message_id"],
        proposed_action=proposal["proposed_action"],
        requested_by=actor_id,
    )
    now = datetime.now(timezone.utc)
    await repository.mark_cleanup_proposal_decided(
        connection,
        proposal_id=proposal_id,
        status="approved",
        decided_at=now,
        gmail_action_command_id=command.id,
    )
    logger.info(
        "정리 제안 승인 — Gmail 커맨드 요청",
        proposal_id=str(proposal_id),
        command_id=str(command.id),
    )
    return await repository.get_cleanup_proposal(connection, proposal_id=proposal_id)


async def list_cleanup_queue(connection: AsyncConnection, *, workspace_id: uuid.UUID) -> list[dict]:
    return await repository.list_cleanup_review_queue(connection, workspace_id=workspace_id)
