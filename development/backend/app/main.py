from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from app.api.deps import get_database_check, get_redis_check
from app.api.router import api_router
from app.core.config import settings
from app.core.discovery import register_discovered_jobs
from app.core.error_handlers import maily_error_handler, unhandled_exception_handler
from app.core.errors import MailyError
from app.core.logging import RequestContextMiddleware, configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Domain job handlers are registered here (server startup), not at
    # module import time — importing app.main to build a TestClient
    # shouldn't mutate the global job registry as a side effect.
    register_discovered_jobs()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.include_router(api_router)
app.add_exception_handler(MailyError, maily_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


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
