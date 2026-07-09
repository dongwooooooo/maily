from app.domains.identity.router import router as router

JOB_HANDLERS: dict = {}
EVENT_CONSUMERS: dict = {}
PURGE_HANDLER = None
