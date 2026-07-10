import uuid
from datetime import datetime

from pydantic import BaseModel

# status enum values — fixed by _integration-contract.md §5.
JOB_STATUSES = {"queued", "running", "succeeded", "failed"}
RULE_SUGGESTION_STATUSES = {"pending", "approved", "rejected"}
CLEANUP_PROPOSAL_STATUSES = {"pending", "approved", "rejected", "applied"}


class MessageSummary(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    summary_text: str | None
    is_metadata_only: bool
    summary_version: int
    model_name: str | None


class MessageImportanceClassification(BaseModel):
    """Full internal view — includes `reason`. Callers building a public
    API response must go through `importance.to_public_view()` instead,
    which drops `reason` by default per the "AI 판단 이유는 기본으로 노출하지
    않는다" top-level principle."""

    id: uuid.UUID
    message_id: uuid.UUID
    importance_band: str
    reason: str
    classification_version: int


class RuleSuggestion(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    correction_signal_id: uuid.UUID
    suggested_condition: dict
    status: str
    decided_at: datetime | None


class ClassificationRule(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    service_label_id: uuid.UUID
    match_condition: dict
    active: bool


class RulesView(BaseModel):
    """GET /rules response shape — pending suggestions + active rules."""

    suggestions: list[RuleSuggestion]
    rules: list[ClassificationRule]


class CleanupProposal(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    message_id: uuid.UUID
    proposed_action: str
    confidence_band: str
    status: str
    before_state: dict
    after_state: dict | None
    gmail_action_command_id: uuid.UUID | None
    decided_at: datetime | None
