"""AssistantLLMPort: the only way assistant_decisions talks to an LLM.

module-boundaries.md invariant "LLM payload는 최소만 — subject/sender/snippet/
labels/limited excerpt. raw body·raw prompt는 어떤 테이블에도 저장 안 함."
This port's method *signatures* enforce that boundary structurally: every
input TypedDict below only has room for the allowed metadata fields. There
is no parameter through which a caller could pass a raw email body or a
freeform prompt string — the privacy contract is unrepresentable to violate
via this interface, not just "policy that could be forgotten".

fake_llm.py provides the only implementation until a real LLM provider is
selected (assistant_decisions.md "fake_llm 계약"). Job code depends on this
abstract type via get_llm()/set_llm(), never on a concrete provider client.
"""

from abc import ABC, abstractmethod
from typing import TypedDict


class SummaryInput(TypedDict):
    subject: str | None
    sender: str | None
    snippet: str | None
    labels: list[str]
    excerpt: str | None


class SummaryOutcome(TypedDict):
    summary_text: str | None
    is_metadata_only: bool
    model_name: str


class ImportanceInput(TypedDict):
    subject: str | None
    sender: str | None
    snippet: str | None
    labels: list[str]
    is_read: bool


class ImportanceOutcome(TypedDict):
    importance_band: str
    reason: str


class CleanupSignal(TypedDict):
    is_read: bool
    is_archived: bool
    label_names: list[str]


class CleanupAssessment(TypedDict):
    confidence_band: str
    proposed_action: str | None


class AssistantLLMPort(ABC):
    """Metadata-only evaluation. No method here accepts a raw message body
    or a freeform prompt string — see module docstring."""

    @abstractmethod
    def summarize(self, payload: SummaryInput) -> SummaryOutcome:
        """Produce a short summary from allowed metadata fields only."""

    @abstractmethod
    def classify_importance(self, payload: ImportanceInput) -> ImportanceOutcome:
        """Produce an importance band + reason from allowed metadata fields only."""

    @abstractmethod
    def assess_cleanup(self, signal: CleanupSignal) -> CleanupAssessment:
        """Produce a confidence band (+ proposed action, if any) for a
        cleanup candidate from read/archive/label state only."""


_active_llm: AssistantLLMPort | None = None


def set_llm(llm: AssistantLLMPort | None) -> None:
    """Service-locator hook, mirrors mail_intake.gmail_reader.set_reader().
    Tests inject a fresh FakeAssistantLLM per test; reset to None in
    teardown. Default (nothing set) is a fresh FakeAssistantLLM()."""
    global _active_llm
    _active_llm = llm


def get_llm() -> AssistantLLMPort:
    global _active_llm
    if _active_llm is None:
        from app.domains.assistant_decisions.fake_llm import FakeAssistantLLM

        _active_llm = FakeAssistantLLM()
    return _active_llm
