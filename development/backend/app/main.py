from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.api.deps import get_database_check, get_redis_check
from app.api.router import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(
    database_ok: bool = Depends(get_database_check),
    redis_ok: bool = Depends(get_redis_check),
) -> JSONResponse:
    all_ok = database_ok and redis_ok
    body = {
        "status": "ok" if all_ok else "error",
        "checks": {
            "database": "ok" if database_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    }
    return JSONResponse(status_code=200 if all_ok else 503, content=body)
