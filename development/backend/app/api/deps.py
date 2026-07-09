from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.database import check_database_connection, engine
from app.core.redis import check_redis_connection


async def get_database_check() -> bool:
    return await check_database_connection()


async def get_redis_check() -> bool:
    return await check_redis_connection()


async def get_db_connection() -> AsyncIterator[AsyncConnection]:
    async with engine.begin() as connection:
        yield connection
