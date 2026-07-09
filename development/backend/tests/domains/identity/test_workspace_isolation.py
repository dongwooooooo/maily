import uuid

from app.core.database import engine
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login, issue_session, resolve_request_context


async def test_user_a_session_never_resolves_to_user_b_workspace() -> None:
    profile_a = GoogleProfile(google_subject=str(uuid.uuid4()), email="a@example.com")
    profile_b = GoogleProfile(google_subject=str(uuid.uuid4()), email="b@example.com")

    async with engine.begin() as connection:
        result_a = await google_login(connection, profile_a)
    async with engine.begin() as connection:
        result_b = await google_login(connection, profile_b)

    async with engine.begin() as connection:
        token_a = await issue_session(
            connection, user_id=result_a.user_id, workspace_id=result_a.workspace_id
        )

    async with engine.begin() as connection:
        context = await resolve_request_context(connection, token_a)

    assert context.workspace_id == result_a.workspace_id
    assert context.workspace_id != result_b.workspace_id
    assert context.user_id != result_b.user_id
