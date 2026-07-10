from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_database_check, get_redis_check
from app.api.router import api_router
from app.api.schemas import ErrorResponse
from app.core.config import settings
from app.core.discovery import register_discovered_jobs
from app.core.error_handlers import (
    maily_error_handler,
    request_validation_error_handler,
    unhandled_exception_handler,
)
from app.core.errors import MailyError
from app.core.logging import RequestContextMiddleware, configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Domain job handler는 module import 시점이 아니라 여기(server startup)에서
    # 등록한다. TestClient를 만들려고 app.main을 import하는 것만으로 global job
    # registry가 side effect로 변경되면 안 된다.
    register_discovered_jobs()
    yield


def _operation_id_from_route_name(route: APIRoute) -> str:
    # operationId = 라우트 함수명. 프론트 codegen(openapi-typescript)이
    # 함수명을 그대로 클라이언트 메서드 이름으로 쓰므로, 도메인 전체에서
    # 라우트 함수명이 유일해야 한다 — tests/api/test_openapi_metadata.py가 강제.
    return route.name


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    generate_unique_id_function=_operation_id_from_route_name,
)
app.add_middleware(RequestContextMiddleware)
# 인증이 Authorization 헤더 기반(쿠키 없음)이라 credentials 없이 origin 허용만
# 으로 충분하다 — Next rewrites 프록시는 병행하지 않는다(_integration-contract §6).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)
# 에러 봉투는 API 라우트 전체에 중앙 1곳에서 문서화한다 — 엔드포인트 26개에
# responses=를 개별로 다는 대신 include 시점 일괄 부여 (/health,/ready 제외).
app.include_router(
    api_router,
    responses={
        422: {"model": ErrorResponse},
        "default": {"model": ErrorResponse, "description": "Maily error envelope"},
    },
)
app.add_exception_handler(MailyError, maily_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]


@app.get("/ready", responses={200: {"model": ReadyResponse}, 503: {"model": ReadyResponse}})
async def ready(
    database_ok: bool = Depends(get_database_check),
    redis_ok: bool = Depends(get_redis_check),
) -> JSONResponse:
    all_ok = database_ok and redis_ok
    # JSONResponse 직접 반환은 FastAPI response_model 검증을 건너뛰므로,
    # 문서화된 ReadyResponse를 반드시 경유해 스키마-런타임 드리프트를 막는다.
    body = ReadyResponse(
        status="ok" if all_ok else "error",
        checks={
            "database": "ok" if database_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    )
    return JSONResponse(status_code=200 if all_ok else 503, content=body.model_dump())
