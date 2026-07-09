"""`execute_action` job — docs/goals/backend-plans/gmail_actions.md "Job: execute_action".

Triggered (conceptually) by `gmail_action_requested`; payload
`{command_id}`, lock_key `command:{command_id}` (see
_integration-contract.md §2). Task 9 only wires the handler function and
tests it directly — the outbox->job_runs dispatch wiring for this event is a
later integration step (see caller instructions), not part of this task.
"""

import uuid
from datetime import datetime, timezone

import structlog

from app.core.errors import MailyError
from app.core.outbox import append_event
from app.domains.gmail_actions import activity, events, repository
from app.domains.gmail_actions.fake_mutator import FakeGmailMutationPort
from app.domains.gmail_actions.gmail_mutator import GmailMutationPort

logger = structlog.get_logger()

# Module-level mutator singleton. Defaults to the fake port (this domain's
# POC gate G4 only requires the fake contract — see module-boundaries.md
# "모듈별 차단 조건: gmail_actions"). Task 14 swaps this for
# LiveGmailMutationPort via set_mutator() during real app startup; tests call
# set_mutator() with a fresh FakeGmailMutationPort() per test to avoid
# cross-test state bleed.
_mutator: GmailMutationPort = FakeGmailMutationPort()


def set_mutator(mutator: GmailMutationPort) -> None:
    global _mutator
    _mutator = mutator


def get_mutator() -> GmailMutationPort:
    return _mutator


async def _finalize_undo_if_reverse(connection, *, command_id: uuid.UUID) -> None:
    """If this just-applied command is the reverse of an in-flight undo,
    close out the original command (compensating -> undone) — see
    gmail_actions.md "Command: undo_gmail_action" §정상.
    """
    reverse_link = await repository.get_undo_action_by_reverse_command(
        connection, reverse_command_id=command_id
    )
    if reverse_link is None or reverse_link["undone_at"] is not None:
        return

    original = await repository.get_command(
        connection, command_id=reverse_link["original_command_id"]
    )
    if original is None or original["status"] != "compensating":
        return

    new_version = original["version"] + 1
    now = datetime.now(timezone.utc)
    await repository.mark_command_undone(
        connection, command_id=original["id"], version=new_version
    )
    await repository.mark_undo_action_undone(
        connection, undo_id=reverse_link["id"], undone_at=now
    )
    await append_event(
        connection,
        event_type=events.GMAIL_ACTION_UNDONE,
        producer_domain="gmail_actions",
        payload={"command_id": str(original["id"])},
        idempotency_key=events.undone_key(original["id"], new_version),
    )


async def run_execute_action(connection, *, command_id: uuid.UUID) -> None:
    command = await repository.lock_command_for_update(connection, command_id=command_id)
    if command is None:
        logger.warning("존재하지 않는 command_id로 execute_action 호출", command_id=str(command_id))
        return

    if command["status"] == "pending":
        scope = await repository.get_connected_account_scope(
            connection, connected_account_id=command["connected_account_id"]
        )
        if scope is None or scope["status"] in ("disconnecting", "disconnected"):
            # [선행조건] account disconnecting/disconnected -> stop, leave
            # status as pending; purge owns cleanup for this source.
            logger.info(
                "계정 연결 해제 중이라 액션 실행 보류",
                command_id=str(command_id),
                account_status=None if scope is None else scope["status"],
            )
            return

        now = datetime.now(timezone.utc)
        try:
            result = await get_mutator().apply(connection, command_id=command_id)
        except MailyError as exc:
            new_version = command["version"] + 1
            await repository.mark_command_failed(
                connection,
                command_id=command_id,
                version=new_version,
                error_reason=str(exc),
                failed_at=now,
            )
            await append_event(
                connection,
                event_type=events.GMAIL_ACTION_FAILED,
                producer_domain="gmail_actions",
                payload={"command_id": str(command_id)},
                idempotency_key=events.failed_key(command_id, new_version),
            )
            logger.warning("Gmail 액션 실패", command_id=str(command_id), reason=str(exc))
            return

        new_version = command["version"] + 1
        await repository.mark_command_applied(
            connection,
            command_id=command_id,
            version=new_version,
            changed=result.changed,
            applied_at=now,
        )
        command = {
            **command,
            "status": "applied",
            "version": new_version,
            "changed": result.changed,
            "applied_at": now,
        }
        await append_event(
            connection,
            event_type=events.GMAIL_ACTION_APPLIED,
            producer_domain="gmail_actions",
            payload={"command_id": str(command_id)},
            idempotency_key=events.applied_key(command_id, new_version),
        )
        logger.info("Gmail 액션 적용 완료", command_id=str(command_id), changed=result.changed)
    elif command["status"] != "applied":
        # failed/compensating/undone are terminal or owned by a different
        # in-flight path — [선행조건] guard against re-execution.
        return

    # command is applied (freshly, or already was — at-least-once redelivery)
    # -> ensure activity_log/undo_actions exist, backfilling from the ledger
    # if a prior attempt applied Gmail but crashed before committing them.
    scope = await repository.get_connected_account_scope(
        connection, connected_account_id=command["connected_account_id"]
    )
    if scope is not None:
        await activity.ensure_activity_and_undo(
            connection,
            command=command,
            workspace_id=scope["workspace_id"],
            actor_id=command["requested_by"],
        )

    await _finalize_undo_if_reverse(connection, command_id=command_id)


async def execute_action_job(payload: dict) -> None:
    """JOB_HANDLERS["execute_action"] entry point — see __init__.py."""
    from app.core.database import engine

    command_id = uuid.UUID(str(payload["command_id"]))
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command_id)
