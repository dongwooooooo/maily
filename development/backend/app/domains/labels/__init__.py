from app.domains.labels.purge import purge_source
from app.domains.labels.router import router as router

JOB_HANDLERS: dict = {}
EVENT_CONSUMERS: dict = {}
PURGE_HANDLER = purge_source
