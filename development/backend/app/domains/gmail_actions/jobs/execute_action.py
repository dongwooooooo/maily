"""`execute_action` job — docs/goals/backend-plans/gmail_actions.md "Job: execute_action".

개념적으로 `gmail_action_requested`가 trigger한다. payload는 `{command_id}`, lock_key는
`command:{command_id}`다(_integration-contract.md §2 참고). Task 9는 handler function만
wire하고 직접 test한다. 이 event의 outbox->job_runs dispatch wiring은 이후 integration
step이며(caller instructions 참고), 이 task 범위가 아니다.
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

# module-level mutator singleton. 기본값은 fake port다(이 domain의 POC gate G4는 fake
# contract만 요구 — module-boundaries.md "모듈별 차단 조건: gmail_actions" 참고).
# Task 14는 real app startup 중 set_mutator()로 이를 LiveGmailMutationPort로 교체한다.
# test는 cross-test state bleed를 피하려고 test마다 fresh FakeGmailMutationPort()로
# set_mutator()를 호출한다.
_mutator: GmailMutationPort = FakeGmailMutationPort()


def set_mutator(mutator: GmailMutationPort) -> None:
    global _mutator
    _mutator = mutator


def get_mutator() -> GmailMutationPort:
    return _mutator


async def _finalize_undo_if_reverse(connection, *, command_id: uuid.UUID) -> None:
    """방금 applied된 command가 in-flight undo의 reverse라면 original command를 마감한다.

    transition은 compensating -> undone이다. gmail_actions.md
    "Command: undo_gmail_action" §정상 참고.
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
    scope = await repository.get_connected_account_scope(
        connection, connected_account_id=original["connected_account_id"]
    )
    if scope is None:
        # 위 ledger transition은 그대로 유효하고 derived event만 건너뛴다. 아직 PURGE_HANDLER가
        # 없어서(mail_sources/__init__.py) connected_gmail_accounts row는 현재 hard-delete되지
        # 않는다. 그래도 나중에 hard-delete가 생기는 날을 대비해, purged account의 undo가
        # build_briefing에서 실패할 workspace_id: null event를 emit하지 않게 막는다
        # (code review가 잡은 실제 bug: uuid.UUID("None")이 raise하고 retry를 소진한 뒤,
        # user에게 보이는 error 없이 job이 `failed`가 됨).
        logger.warning(
            "undo 대상 계정이 사라져 gmail_action_undone 발행 생략",
            command_id=str(original["id"]),
        )
        return
    await append_event(
        connection,
        event_type=events.GMAIL_ACTION_UNDONE,
        producer_domain="gmail_actions",
        payload={
            "command_id": str(original["id"]),
            "workspace_id": str(scope["workspace_id"]),
            "message_id": str(original["message_id"]) if original["message_id"] else None,
        },
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
            # [선행조건] account가 disconnecting/disconnected면 중단하고 status는 pending으로 둔다.
            # 이 source의 cleanup은 purge가 소유한다.
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
                payload={
                    "command_id": str(command_id),
                    "workspace_id": str(scope["workspace_id"]),
                    "version": new_version,
                    "connected_account_id": str(command["connected_account_id"]),
                },
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
            payload={
                "command_id": str(command_id),
                "workspace_id": str(scope["workspace_id"]),
                "message_id": str(command["message_id"]) if command["message_id"] else None,
                "add_label_ids": command["payload"].get("add_label_ids") or [],
                "remove_label_ids": command["payload"].get("remove_label_ids") or [],
            },
            idempotency_key=events.applied_key(command_id, new_version),
        )
        logger.info("Gmail 액션 적용 완료", command_id=str(command_id), changed=result.changed)
    elif command["status"] != "applied":
        # failed/compensating/undone은 terminal이거나 다른 in-flight path가 소유한다.
        # [선행조건] re-execution guard.
        return

    # command는 applied 상태다(fresh하게 또는 이미 applied — at-least-once redelivery).
    # activity_log/undo_actions 존재를 보장하고, 이전 attempt가 Gmail을 적용한 뒤 commit 전에
    # crash났다면 ledger에서 backfill한다.
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
    """JOB_HANDLERS["execute_action"] entry point — __init__.py 참고."""
    from app.core.database import engine

    command_id = uuid.UUID(str(payload["command_id"]))
    async with engine.begin() as connection:
        await run_execute_action(connection, command_id=command_id)
