"""Deterministic AssistantLLMPort double for TDD — assistant_decisions.md
"fake_llm 계약". `importance_band`/`confidence_band` value sets are
`[미정]` in db-schema.md until the LLM POC lands real thresholds; these
FAKE_* constants are the only place their string values are pinned for
now. Tests and job code reference the constants, never the literal
strings, so a future real-provider swap only touches this module.

Same seed input -> same output every call; no randomness, no clock reads,
no network calls.
"""

from app.core.errors import ExternalServiceError
from app.domains.assistant_decisions.llm import (
    AssistantLLMPort,
    CleanupAssessment,
    CleanupSignal,
    ImportanceInput,
    ImportanceOutcome,
    SummaryInput,
    SummaryOutcome,
)

FAKE_MODEL_NAME = "fake-llm-v1"

FAKE_BAND_URGENT = "urgent"
FAKE_BAND_NORMAL = "normal"
FAKE_BAND_LOW = "low"

FAKE_CONFIDENCE_AUTO_APPLY = "auto-apply"
FAKE_CONFIDENCE_APPROVAL_REQUIRED = "approval-required"
FAKE_CONFIDENCE_SILENT = "silent"

_SUMMARY_EXCERPT_LIMIT = 120


class FakeAssistantLLM(AssistantLLMPort):
    """Test helpers `fail_next_*` make the next call to that method raise
    ExternalServiceError once, to exercise the [부분실패]/job-failed path
    deterministically (mirrors gmail_actions.fake_mutator's fail_next)."""

    def __init__(self) -> None:
        self._fail_next_summarize = False
        self._fail_next_classify_importance = False
        self._fail_next_assess_cleanup = False

    def fail_next_summarize(self) -> None:
        self._fail_next_summarize = True

    def fail_next_classify_importance(self) -> None:
        self._fail_next_classify_importance = True

    def fail_next_assess_cleanup(self) -> None:
        self._fail_next_assess_cleanup = True

    def summarize(self, payload: SummaryInput) -> SummaryOutcome:
        if self._fail_next_summarize:
            self._fail_next_summarize = False
            raise ExternalServiceError("simulated LLM failure (summarize)")

        snippet = (payload.get("snippet") or "").strip()
        subject = (payload.get("subject") or "").strip()

        if not snippet:
            # metadata-only fallback: no snippet to summarize from -> fall
            # back to subject-only text instead of failing the job.
            return SummaryOutcome(
                summary_text=subject or None,
                is_metadata_only=True,
                model_name=FAKE_MODEL_NAME,
            )

        headline = subject or "(제목 없음)"
        summary_text = f"{headline} — {snippet[:_SUMMARY_EXCERPT_LIMIT]}"
        return SummaryOutcome(
            summary_text=summary_text, is_metadata_only=False, model_name=FAKE_MODEL_NAME
        )

    def classify_importance(self, payload: ImportanceInput) -> ImportanceOutcome:
        if self._fail_next_classify_importance:
            self._fail_next_classify_importance = False
            raise ExternalServiceError("simulated LLM failure (classify_importance)")

        labels = set(payload.get("labels") or [])

        if "IMPORTANT" in labels:
            return ImportanceOutcome(
                importance_band=FAKE_BAND_URGENT, reason="발신자가 IMPORTANT 라벨을 지정한 메일"
            )
        if not payload.get("is_read", False):
            return ImportanceOutcome(
                importance_band=FAKE_BAND_NORMAL, reason="아직 읽지 않은 메일"
            )
        return ImportanceOutcome(
            importance_band=FAKE_BAND_LOW, reason="이미 읽은 일반 메일"
        )

    def assess_cleanup(self, signal: CleanupSignal) -> CleanupAssessment:
        if self._fail_next_assess_cleanup:
            self._fail_next_assess_cleanup = False
            raise ExternalServiceError("simulated LLM failure (assess_cleanup)")

        labels = set(signal.get("label_names") or [])

        if signal.get("is_archived", False) or not signal.get("is_read", False):
            # already archived, or still unread -> nothing to propose yet.
            return CleanupAssessment(confidence_band=FAKE_CONFIDENCE_SILENT, proposed_action=None)

        if "PROMOTIONS" in labels:
            return CleanupAssessment(
                confidence_band=FAKE_CONFIDENCE_AUTO_APPLY, proposed_action="archive"
            )

        return CleanupAssessment(
            confidence_band=FAKE_CONFIDENCE_APPROVAL_REQUIRED, proposed_action="archive"
        )
