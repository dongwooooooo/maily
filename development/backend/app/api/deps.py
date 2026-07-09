from collections.abc import AsyncIterator

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import security
from app.core.database import check_database_connection, engine
from app.core.errors import UnauthorizedError
from app.core.redis import check_redis_connection


async def get_database_check() -> bool:
    return await check_database_connection()


async def get_redis_check() -> bool:
    return await check_redis_connection()


async def get_db_connection() -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as connection:
        yield connection


async def get_bearer_token(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    return authorization.removeprefix("Bearer ")


async def get_request_context(
    token: str = Depends(get_bearer_token),
    connection: AsyncConnection = Depends(get_db_connection),
):
    from app.domains.identity.schemas import RequestContext
    from app.domains.identity.service import resolve_request_context

    try:
        context: RequestContext = await resolve_request_context(connection, token)
    except security.InvalidSessionTokenError as exc:
        raise UnauthorizedError("invalid session") from exc
    return context
