from app.domains.mail_sources.router import router as router

JOB_HANDLERS: dict = {}
EVENT_CONSUMERS: dict = {}
PURGE_HANDLER = None
