from app.domains.gmail_actions.jobs.execute_action import execute_action_job
from app.domains.gmail_actions.purge import purge_source
from app.domains.gmail_actions.router import router as router

JOB_HANDLERS: dict = {"execute_action": execute_action_job}
EVENT_CONSUMERS: dict = {"gmail_action_requested": ["execute_action"]}
PURGE_HANDLER = purge_source
