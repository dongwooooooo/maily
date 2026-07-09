from fastapi import APIRouter

from app.domains import identity, mail_sources

api_router = APIRouter()
api_router.include_router(identity.router, prefix="/auth", tags=["auth"])
api_router.include_router(mail_sources.router, prefix="/sources", tags=["sources"])
