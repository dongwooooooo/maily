import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import security
from app.domains.identity import repository
from app.domains.identity.schemas import GoogleLoginResult, GoogleProfile, RequestContext

DEFAULT_SESSION_TTL = timedelta(hours=12)


async def google_login(
    connection: AsyncConnection, profile: GoogleProfile
) -> GoogleLoginResult:
    """Resolve a Google OAuth callback profile to a user/workspace.

    A new google_subject creates one user, one workspace, and one
    owner membership. A known google_subject reuses its existing
    workspace and only touches last_login_at — it never creates a
    second workspace for the same person.
    """
    now = datetime.now(timezone.utc)
    existing = await repository.find_user_by_google_subject(
        connection, google_subject=profile.google_subject
    )

    if existing is not None:
        await repository.touch_last_login(connection, user_id=existing["id"], last_login_at=now)
        workspace_id = await repository.find_workspace_id_for_user(
            connection, user_id=existing["id"]
        )
        return GoogleLoginResult(
            user_id=existing["id"], workspace_id=workspace_id, is_new_user=False
        )

    user_id, workspace_id = await repository.create_user_workspace_membership(
        connection,
        google_subject=profile.google_subject,
        email=profile.email,
        display_name=profile.display_name,
        last_login_at=now,
    )
    return GoogleLoginResult(user_id=user_id, workspace_id=workspace_id, is_new_user=True)


async def issue_session(
    connection: AsyncConnection,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    ttl: timedelta = DEFAULT_SESSION_TTL,
) -> str:
    session_id = uuid.uuid4()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + ttl

    await repository.insert_session(
        connection,
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    return security.sign_session_token(
        session_id=session_id,
        user_id=user_id,
        workspace_id=workspace_id,
        issued_at=issued_at,
        expires_at=expires_at,
    )


async def resolve_request_context(connection: AsyncConnection, token: str) -> RequestContext:
    """Verify a session token and resolve it to its owning user/workspace.

    workspace_id always comes from the session row the token points
    at — never from a caller-supplied parameter — so a valid token
    can only ever resolve to the workspace it was issued for.
    """
    claims = security.verify_session_token(token)
    session_id = uuid.UUID(claims["session_id"])

    session_row = await repository.find_session(connection, session_id=session_id)
    if session_row is None or session_row["revoked_at"] is not None:
        raise security.InvalidSessionTokenError("session revoked or not found")

    return RequestContext(
        user_id=session_row["user_id"], workspace_id=session_row["workspace_id"]
    )
