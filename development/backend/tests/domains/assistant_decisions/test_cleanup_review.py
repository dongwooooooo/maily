import uuid
from datetime import datetime, timezone

from app.core.database import engine
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.domains.assistant_decisions import repository
from app.domains.assistant_decisions.cleanup import (
    approve_cleanup_proposal,
    list_cleanup_queue,
    prepare_cleanup_proposals,
)
from app.domains.gmail_actions.models import gmail_action_commands
from tests.domains.assistant_decisions.conftest import (
    seed_message,
    seed_message_labels,
    seed_scope,
)


async def test_rerun_does_not_duplicate_pending_proposal() -> None:
    """[멱등] 같은 message+action 조합으로 두 번 실행해도 pending proposal이
    하나만 유지된다(assistant_decisions.md "같은 후보 중복 proposal 방지")."""
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])

    async with engine.begin() as connection:
        first = await prepare_cleanup_proposals(
            connection,
            workspace_id=workspace_id,
            message_ids=[message_id],
            requested_by=user_id,
        )
        second = await prepare_cleanup_proposals(
            connection,
            workspace_id=workspace_id,
            message_ids=[message_id],
            requested_by=user_id,
        )

    async with engine.connect() as connection:
        count = await repository.count_cleanup_proposals_for_message(connection, message_id=message_id)

    assert count == 1
    assert first[0]["id"] == second[0]["id"]


async def test_confidence_band_routes_proposal() -> None:
    """[정상] read+PROMOTIONS -> auto-apply (즉시 command 요청, status=approved).
    read+no-promo-label -> approval-required (승인 큐 pending)."""
    workspace_id, user_id, account_id = await seed_scope()
    auto_message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(auto_message_id, ["INBOX", "PROMOTIONS"])
    review_message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(review_message_id, ["INBOX"])

    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection,
            workspace_id=workspace_id,
            message_ids=[auto_message_id, review_message_id],
            requested_by=user_id,
        )

    by_message = {p["message_id"]: p for p in proposals}
    auto_proposal = by_message[auto_message_id]
    review_proposal = by_message[review_message_id]

    assert auto_proposal["confidence_band"] == "auto-apply"
    assert auto_proposal["status"] == "approved"
    assert auto_proposal["gmail_action_command_id"] is not None

    assert review_proposal["confidence_band"] == "approval-required"
    assert review_proposal["status"] == "pending"
    assert review_proposal["gmail_action_command_id"] is None


async def test_silent_makes_no_proposal() -> None:
    """[선행조건] 아직 안 읽은 메일 -> silent, proposal row 자체가 생기지 않는다."""
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=False, is_archived=False)
    await seed_message_labels(message_id, ["INBOX", "UNREAD"])

    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )

    assert proposals == []
    async with engine.connect() as connection:
        count = await repository.count_cleanup_proposals_for_message(
            connection, message_id=message_id
        )
    assert count == 0


async def test_proposal_before_after_no_raw_body() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])

    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )

    proposal = proposals[0]
    for state in (proposal["before_state"], proposal["after_state"]):
        assert set(state.keys()) == {"is_read", "is_archived", "labels"}
    assert proposal["before_state"]["is_archived"] is False
    assert proposal["after_state"]["is_archived"] is True
    assert "INBOX" not in proposal["after_state"]["labels"]


async def test_approve_one_requests_command_not_gmail() -> None:
    """[정상] 승인 -> gmail_actions command 요청만(=pending row 생성).
    Gmail을 직접 호출하지 않는다 — request_gmail_action은 그 자체로 Gmail을
    호출하지 않는 순수 command-ledger insert이므로, 이 테스트는 command가
    'pending' 상태로 생성됐는지(즉 실제 Gmail mutation이 실행되지 않았는지)로
    검증한다."""
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])

    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )
    proposal_id = proposals[0]["id"]
    assert proposals[0]["status"] == "pending"  # approval-required, 아직 결정 전

    async with engine.begin() as connection:
        approved = await approve_cleanup_proposal(
            connection, proposal_id=proposal_id, workspace_id=workspace_id, actor_id=user_id
        )

    assert approved["status"] == "approved"
    assert approved["gmail_action_command_id"] is not None

    async with engine.connect() as connection:
        from sqlalchemy import select

        command_row = (
            await connection.execute(
                select(gmail_action_commands).where(
                    gmail_action_commands.c.id == approved["gmail_action_command_id"]
                )
            )
        ).mappings().first()
    assert command_row is not None
    assert command_row["status"] == "pending"  # applied 아님 — Gmail call 없음


async def test_no_approve_all_endpoint() -> None:
    """[데이터경계] approve-all 엔드포인트 없음 — cleanup.py에 벌크 승인 함수
    자체가 존재하지 않는다는 걸 모듈 심볼로 검증."""
    import app.domains.assistant_decisions.cleanup as cleanup_module

    assert not hasattr(cleanup_module, "approve_all_cleanup_proposals")
    assert not any("approve_all" in name for name in dir(cleanup_module))


async def test_approve_only_pending_approval_required() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])
    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )
    proposal_id = proposals[0]["id"]

    async with engine.begin() as connection:
        await repository.mark_cleanup_proposal_decided(
            connection,
            proposal_id=proposal_id,
            status="rejected",
            decided_at=datetime.now(timezone.utc),
            gmail_action_command_id=None,
        )

    async with engine.begin() as connection:
        try:
            await approve_cleanup_proposal(
                connection, proposal_id=proposal_id, workspace_id=workspace_id, actor_id=user_id
            )
            assert False, "expected ConflictError"
        except ConflictError:
            pass


async def test_approve_scoped_to_workspace() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(message_id, ["INBOX"])
    async with engine.begin() as connection:
        proposals = await prepare_cleanup_proposals(
            connection, workspace_id=workspace_id, message_ids=[message_id], requested_by=user_id
        )
    proposal_id = proposals[0]["id"]

    other_workspace_id = uuid.uuid4()
    async with engine.begin() as connection:
        try:
            await approve_cleanup_proposal(
                connection,
                proposal_id=proposal_id,
                workspace_id=other_workspace_id,
                actor_id=user_id,
            )
            assert False, "expected ForbiddenError"
        except ForbiddenError:
            pass


async def test_proposal_not_found_raises() -> None:
    workspace_id, user_id, _ = await seed_scope()
    async with engine.begin() as connection:
        try:
            await approve_cleanup_proposal(
                connection, proposal_id=uuid.uuid4(), workspace_id=workspace_id, actor_id=user_id
            )
            assert False, "expected NotFoundError"
        except NotFoundError:
            pass


async def test_list_cleanup_only_approval_required() -> None:
    workspace_id, user_id, account_id = await seed_scope()
    auto_message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(auto_message_id, ["INBOX", "PROMOTIONS"])
    review_message_id = await seed_message(account_id, is_read=True, is_archived=False)
    await seed_message_labels(review_message_id, ["INBOX"])
    silent_message_id = await seed_message(account_id, is_read=False, is_archived=False)
    await seed_message_labels(silent_message_id, ["INBOX", "UNREAD"])

    async with engine.begin() as connection:
        await prepare_cleanup_proposals(
            connection,
            workspace_id=workspace_id,
            message_ids=[auto_message_id, review_message_id, silent_message_id],
            requested_by=user_id,
        )

    async with engine.connect() as connection:
        queue = await list_cleanup_queue(connection, workspace_id=workspace_id)

    assert len(queue) == 1
    assert queue[0]["message_id"] == review_message_id
    assert queue[0]["confidence_band"] == "approval-required"
