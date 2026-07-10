"""TDD용 deterministic AssistantLLMPort double — assistant_decisions.md
"fake_llm 계약". `importance_band`/`confidence_band` value set은 LLM POC가 실제
threshold를 확정할 때까지 db-schema.md에서 `[미정]`이다. 지금은 이 FAKE_* constant만
해당 문자열 값을 고정한다. test와 job code는 literal string이 아니라 constant를 참조하므로
미래 real-provider 교체는 이 module만 건드리면 된다.

같은 seed input -> 매 호출 같은 output이다. randomness, clock read, network call은 없다.
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
    """test helper `fail_next_*`는 해당 method의 다음 호출이 ExternalServiceError를 한 번
    raise하게 만들어 [부분실패]/job-failed path를 deterministic하게 검증한다
    (gmail_actions.fake_mutator의 fail_next와 같은 패턴)."""

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
            # metadata-only fallback: 요약할 snippet이 없으면 job을 실패시키지 않고
            # subject-only text로 fallback한다.
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
            # 이미 archived이거나 아직 unread면 아직 제안할 것이 없다.
            return CleanupAssessment(confidence_band=FAKE_CONFIDENCE_SILENT, proposed_action=None)

        if "PROMOTIONS" in labels:
            return CleanupAssessment(
                confidence_band=FAKE_CONFIDENCE_AUTO_APPLY, proposed_action="archive"
            )

        return CleanupAssessment(
            confidence_band=FAKE_CONFIDENCE_APPROVAL_REQUIRED, proposed_action="archive"
        )
