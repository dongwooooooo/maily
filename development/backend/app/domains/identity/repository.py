import uuid
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domains.identity.models import sessions, users, workspace_members, workspaces


async def find_user_by_google_subject(
    connection: AsyncConnection, *, google_subject: str
) -> dict | None:
    row = (
        await connection.execute(
            select(users).where(users.c.google_subject == google_subject)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def find_workspace_id_for_user(
    connection: AsyncConnection, *, user_id: uuid.UUID
) -> uuid.UUID | None:
    return (
        await connection.execute(
            select(workspace_members.c.workspace_id).where(
                workspace_members.c.user_id == user_id
            )
        )
    ).scalars().first()


async def touch_last_login(
    connection: AsyncConnection, *, user_id: uuid.UUID, last_login_at: datetime
) -> None:
    await connection.execute(
        update(users).where(users.c.id == user_id).values(last_login_at=last_login_at)
    )


async def create_user_workspace_membership(
    connection: AsyncConnection,
    *,
    google_subject: str,
    email: str,
    display_name: str | None,
    last_login_at: datetime,
) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    await connection.execute(
        insert(users).values(
            id=user_id,
            google_subject=google_subject,
            email=email,
            display_name=display_name,
            last_login_at=last_login_at,
        )
    )
    await connection.execute(insert(workspaces).values(id=workspace_id, name=None))
    await connection.execute(
        insert(workspace_members).values(
            id=uuid.uuid4(), workspace_id=workspace_id, user_id=user_id, role="owner"
        )
    )
    return user_id, workspace_id


async def insert_session(
    connection: AsyncConnection,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    issued_at: datetime,
    expires_at: datetime,
) -> None:
    await connection.execute(
        insert(sessions).values(
            id=session_id,
            user_id=user_id,
            workspace_id=workspace_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )
    )


async def find_session(connection: AsyncConnection, *, session_id: uuid.UUID) -> dict | None:
    row = (
        await connection.execute(select(sessions).where(sessions.c.id == session_id))
    ).mappings().first()
    return dict(row) if row is not None else None


async def revoke_session(
    connection: AsyncConnection, *, session_id: uuid.UUID, revoked_at: datetime
) -> None:
    await connection.execute(
        update(sessions).where(sessions.c.id == session_id).values(revoked_at=revoked_at)
    )


async def get_session_summary(
    connection: AsyncConnection, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> dict:
    user_row = (
        await connection.execute(select(users).where(users.c.id == user_id))
    ).mappings().first()
    workspace_row = (
        await connection.execute(select(workspaces).where(workspaces.c.id == workspace_id))
    ).mappings().first()
    return {
        "user_id": user_row["id"],
        "email": user_row["email"],
        "display_name": user_row["display_name"],
        "workspace_id": workspace_row["id"],
        "workspace_name": workspace_row["name"],
    }
