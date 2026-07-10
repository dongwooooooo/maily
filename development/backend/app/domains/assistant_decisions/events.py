"""assistant_decisions event catalog(producer=assistant_decisions).

docs/areas/backend/module-boundaries.md Event Catalog와
docs/goals/backend-plans/assistant_decisions.md "Event 발행 목록"을 mirror한다.
idempotency-key formatting이 summaries.py / importance.py / rules.py / cleanup.py에
중복되지 않도록 단일 module로 유지한다.

band/reason은 event payload field일 뿐이다. 다른 band가 다른 event_type을 만들지는 않는다
(assistant_decisions.md invariant).
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
