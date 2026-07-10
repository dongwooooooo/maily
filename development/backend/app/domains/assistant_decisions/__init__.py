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

# _integration-contract.md §2 job_type -> handler contract 선언.
JOB_HANDLERS: dict = {
    "generate_summary": generate_summary_job,
    "classify_importance": classify_importance_job,
    "create_rule_suggestions": create_rule_suggestions_job,
    "prepare_cleanup_proposals": prepare_cleanup_proposals_job,
}

# _integration-contract.md §3 event -> consumer job_type mapping. 이 event type들의
# 실제 outbox->job_runs dispatch wiring은 이후 integration step이다(이 task는 handler
# 함수만 직접 build+test). task report 참고.
EVENT_CONSUMERS: dict = {
    "gmail_snapshot_changed": [
        "generate_summary",  # summary_enabled일 때만 queued — summaries.py 참고
        "classify_importance",
        "prepare_cleanup_proposals",
    ],
    "label_correction_recorded": ["create_rule_suggestions"],
}

PURGE_HANDLER = purge_source
