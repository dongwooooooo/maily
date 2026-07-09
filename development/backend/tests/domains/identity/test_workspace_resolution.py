import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import security
from app.core.config import settings
from app.core.database import engine
from app.domains.identity import repository
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session, resolve_request_context


async def _login_and_issue_session(**session_kwargs):
    profile = GoogleProfile(google_subject=str(uuid.uuid4()), email="a@example.com")
    async with engine.begin() as connection:
        result = await google_login(connection, profile)
    async with engine.begin() as connection:
        token = await issue_session(
            connection, user_id=result.user_id, workspace_id=result.workspace_id, **session_kwargs
        )
    return result, token


async def test_session_claims_contain_user_workspace_issuer() -> None:
    result, token = await _login_and_issue_session()

    claims = security.verify_session_token(token)

    assert claims["user_id"] == str(result.user_id)
    assert claims["workspace_id"] == str(result.workspace_id)
    assert claims["iss"] == settings.jwt_issuer


async def test_context_scopes_to_session_workspace() -> None:
    result, token = await _login_and_issue_session()

    async with engine.begin() as connection:
        context = await resolve_request_context(connection, token)

    assert context.user_id == result.user_id
    assert context.workspace_id == result.workspace_id


async def test_expired_session_rejected() -> None:
    _, token = await _login_and_issue_session(ttl=timedelta(seconds=-1))

    async with engine.begin() as connection:
        with pytest.raises(security.InvalidSessionTokenError):
            await resolve_request_context(connection, token)


async def test_revoked_session_rejected() -> None:
    _, token = await _login_and_issue_session()
    session_id = uuid.UUID(security.verify_session_token(token)["session_id"])

    async with engine.begin() as connection:
        await repository.revoke_session(
            connection, session_id=session_id, revoked_at=datetime.now(timezone.utc)
        )

    async with engine.begin() as connection:
        with pytest.raises(security.InvalidSessionTokenError):
            await resolve_request_context(connection, token)
