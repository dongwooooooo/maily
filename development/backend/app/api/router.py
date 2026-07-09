from fastapi import APIRouter

from app.domains import identity

api_router = APIRouter()
api_router.include_router(identity.router, prefix="/auth", tags=["auth"])
