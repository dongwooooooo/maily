from app.domains.mail_sources.jobs.purge_disconnected_source import purge_disconnected_source_job
from app.domains.mail_sources.purge import purge_source
from app.domains.mail_sources.router import router as router

JOB_HANDLERS: dict = {"purge_disconnected_source": purge_disconnected_source_job}
EVENT_CONSUMERS: dict = {"gmail_source_disconnected": ["purge_disconnected_source"]}
PURGE_HANDLER = purge_source
