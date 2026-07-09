from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.identity import repository
from app.domains.identity.schemas import GoogleLoginResult, GoogleProfile


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
