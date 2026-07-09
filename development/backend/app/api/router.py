from fastapi import APIRouter

from app.domains import gmail_actions, identity, labels, mail_intake, mail_sources

api_router = APIRouter()
api_router.include_router(identity.router, prefix="/auth", tags=["auth"])
api_router.include_router(mail_sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(mail_intake.router, prefix="/intake", tags=["intake"])
# No prefix: labels.router declares full paths (/labels, /messages/{id}/move) —
# see app/domains/labels/router.py for why a single blanket prefix doesn't fit.
api_router.include_router(labels.router, tags=["labels"])
api_router.include_router(gmail_actions.router, prefix="/actions", tags=["actions"])
