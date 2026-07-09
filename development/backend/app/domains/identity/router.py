import uuid

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_db_connection, get_request_context
from app.domains.identity import repository
from app.domains.identity.oauth import verify_google_id_token
from app.domains.identity.schemas import RequestContext
from app.domains.identity.service import google_login, issue_session

router = APIRouter()


class GoogleCallbackRequest(BaseModel):
    id_token: str


class GoogleCallbackResponse(BaseModel):
    token: str
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    is_new_user: bool


class SessionSummaryResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None
    workspace_id: uuid.UUID
    workspace_name: str | None


def get_google_profile_verifier():
    return verify_google_id_token


@router.post("/google/callback", response_model=GoogleCallbackResponse)
async def google_callback(
    body: GoogleCallbackRequest,
    verify_profile=Depends(get_google_profile_verifier),
    connection: AsyncConnection = Depends(get_db_connection),
) -> GoogleCallbackResponse:
    profile = await verify_profile(body.id_token)
    login_result = await google_login(connection, profile)
    token = await issue_session(
        connection, user_id=login_result.user_id, workspace_id=login_result.workspace_id
    )
    return GoogleCallbackResponse(
        token=token,
        user_id=login_result.user_id,
        workspace_id=login_result.workspace_id,
        is_new_user=login_result.is_new_user,
    )


@router.get("/session", response_model=SessionSummaryResponse)
async def get_session(
    context: RequestContext = Depends(get_request_context),
    connection: AsyncConnection = Depends(get_db_connection),
) -> SessionSummaryResponse:
    structlog.contextvars.bind_contextvars(
        workspace_id=str(context.workspace_id), user_id=str(context.user_id)
    )

    summary = await repository.get_session_summary(
        connection, user_id=context.user_id, workspace_id=context.workspace_id
    )
    return SessionSummaryResponse(**summary)
