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
    """Google OAuth callback profile을 user/workspace로 resolve한다.

    새 google_subject는 user 하나, workspace 하나, owner membership 하나를 만든다.
    알려진 google_subject는 기존 workspace를 재사용하고 last_login_at만 갱신한다. 같은 사람에게
    두 번째 workspace를 만들지 않는다.
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
    """session token을 verify하고 그 소유 user/workspace로 resolve한다.

    workspace_id는 항상 token이 가리키는 session row에서 오며, caller-supplied parameter에서
    오지 않는다. 따라서 valid token은 발급 대상 workspace로만 resolve될 수 있다.
    """
    claims = security.verify_session_token(token)
    session_id = uuid.UUID(claims["session_id"])

    session_row = await repository.find_session(connection, session_id=session_id)
    if session_row is None or session_row["revoked_at"] is not None:
        raise security.InvalidSessionTokenError("session revoked or not found")

    return RequestContext(
        user_id=session_row["user_id"], workspace_id=session_row["workspace_id"]
    )
