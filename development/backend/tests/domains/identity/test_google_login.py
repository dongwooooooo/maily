import uuid

from app.core.database import engine
from app.domains.identity.schemas import GoogleProfile
from app.domains.identity.service import google_login


def _profile(**overrides) -> GoogleProfile:
    defaults = {
        "google_subject": str(uuid.uuid4()),
        "email": "a@example.com",
        "display_name": "A",
    }
    defaults.update(overrides)
    return GoogleProfile(**defaults)


async def test_new_subject_creates_user_workspace_membership() -> None:
    profile = _profile()

    async with engine.begin() as connection:
        result = await google_login(connection, profile)

    assert result.is_new_user is True
    assert result.user_id is not None
    assert result.workspace_id is not None


async def test_relogin_reuses_existing_workspace() -> None:
    profile = _profile()

    async with engine.begin() as connection:
        first = await google_login(connection, profile)

    async with engine.begin() as connection:
        second = await google_login(connection, profile)

    assert second.is_new_user is False
    assert second.user_id == first.user_id
    assert second.workspace_id == first.workspace_id


async def test_same_email_different_subject_is_a_new_user() -> None:
    first_profile = _profile(email="shared@example.com")
    second_profile = _profile(email="shared@example.com")

    async with engine.begin() as connection:
        first = await google_login(connection, first_profile)

    async with engine.begin() as connection:
        second = await google_login(connection, second_profile)

    assert second.is_new_user is True
    assert second.user_id != first.user_id
    assert second.workspace_id != first.workspace_id
