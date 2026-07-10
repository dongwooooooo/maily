from app.domains.assistant_decisions.jobs.classify_importance import classify_importance_job
from app.domains.assistant_decisions.jobs.create_rule_suggestions import (
    create_rule_suggestions_job,
)
from app.domains.assistant_decisions.jobs.generate_summary import generate_summary_job
from app.domains.assistant_decisions.jobs.prepare_cleanup_proposals import (
    prepare_cleanup_proposals_job,
)
from app.domains.assistant_decisions.purge import purge_source
from app.domains.assistant_decisions.router import router as router

# _integration-contract.md §2 job_type -> handler contract.
JOB_HANDLERS: dict = {
    "generate_summary": generate_summary_job,
    "classify_importance": classify_importance_job,
    "create_rule_suggestions": create_rule_suggestions_job,
    "prepare_cleanup_proposals": prepare_cleanup_proposals_job,
}

# _integration-contract.md §3 event -> consumer job_type mapping. Actual
# outbox->job_runs dispatch wiring for these event types is a later
# integration step (this task only builds+tests the handler functions
# directly) — see task report.
EVENT_CONSUMERS: dict = {
    "gmail_snapshot_changed": [
        "generate_summary",  # only queued when summary_enabled — see summaries.py
        "classify_importance",
        "prepare_cleanup_proposals",
    ],
    "label_correction_recorded": ["create_rule_suggestions"],
}

PURGE_HANDLER = purge_source
