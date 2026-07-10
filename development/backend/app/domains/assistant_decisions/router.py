import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.domains.assistant_decisions.cleanup import approve_cleanup_proposal, list_cleanup_queue
from app.domains.assistant_decisions.rules import approve_rule_suggestion, list_rules
from app.domains.assistant_decisions.schemas import CleanupProposal, RuleSuggestion, RulesView
from app.domains.identity.schemas import RequestContext

# _integration-contract.md §3: prefix 없는 full path(/rules, /cleanup)이며,
# labels.router와 같은 패턴이라 blanket prefix 없이 include된다.
router = APIRouter()


@router.get("/rules", response_model=RulesView)
async def get_rules(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> RulesView:
    view = await list_rules(connection, workspace_id=context.workspace_id)
    return RulesView(**view)


@router.post("/rules/{suggestion_id}/approve", response_model=RuleSuggestion)
async def post_approve_rule(
    suggestion_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> RuleSuggestion:
    result = await approve_rule_suggestion(
        connection, suggestion_id=suggestion_id, workspace_id=context.workspace_id
    )
    return RuleSuggestion(**result)


@router.get("/cleanup", response_model=list[CleanupProposal])
async def get_cleanup_queue(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> list[CleanupProposal]:
    queue = await list_cleanup_queue(connection, workspace_id=context.workspace_id)
    return [CleanupProposal(**row) for row in queue]


@router.post("/cleanup/{proposal_id}/approve", response_model=CleanupProposal)
async def post_approve_cleanup(
    proposal_id: uuid.UUID,
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> CleanupProposal:
    result = await approve_cleanup_proposal(
        connection,
        proposal_id=proposal_id,
        workspace_id=context.workspace_id,
        actor_id=context.user_id,
    )
    return CleanupProposal(**result)

# NOTE(coordinator open question): `POST /cleanup/approve-all` 또는
# `POST /rules/approve-all` route는 의도적으로 없다. assistant_decisions.md
# "approve-all 엔드포인트 없음(negative)" 및 test_cleanup_review.py의
# test_no_approve_all_endpoint 참고.
