from app.core.database import check_database_connection
from app.core.redis import check_redis_connection


async def get_database_check() -> bool:
    return await check_database_connection()


async def get_redis_check() -> bool:
    return await check_redis_connection()
