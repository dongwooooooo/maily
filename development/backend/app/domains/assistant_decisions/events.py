"""assistant_decisions event catalog (producer=assistant_decisions).

Mirrors docs/areas/backend/module-boundaries.md Event Catalog and
docs/goals/backend-plans/assistant_decisions.md "Event 발행 목록". Kept as a
single module so idempotency-key formatting isn't duplicated across
summaries.py / importance.py / rules.py / cleanup.py.

band/reason are event payload fields only — a different band never
produces a different event_type (assistant_decisions.md invariant).
"""

import uuid

SUMMARY_COMPLETED = "summary_completed"
IMPORTANCE_CLASSIFIED = "importance_classified"
CLEANUP_PROPOSAL_CREATED = "cleanup_proposal_created"
RULE_SUGGESTION_CREATED = "rule_suggestion_created"


def summary_completed_key(message_id: uuid.UUID, summary_version: int) -> str:
    return f"message:{message_id}:summary:{summary_version}"


def importance_classified_key(message_id: uuid.UUID, classification_version: int) -> str:
    return f"message:{message_id}:importance:{classification_version}"


def cleanup_proposal_created_key(message_id: uuid.UUID, proposal_version: int) -> str:
    return f"message:{message_id}:cleanup:{proposal_version}"


def rule_suggestion_created_key(suggestion_id: uuid.UUID) -> str:
    return f"rule-suggestion:{suggestion_id}:created"
