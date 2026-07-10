"""AssistantLLMPort: assistant_decisions가 LLM과 통신하는 유일한 방법.

module-boundaries.md invariant "LLM payload는 최소만 — subject/sender/snippet/
labels/limited excerpt. raw body·raw prompt는 어떤 테이블에도 저장 안 함."
이 port의 method *signature*는 그 boundary를 구조적으로 강제한다. 아래 input TypedDict는
허용된 metadata field만 담을 수 있다. caller가 raw email body나 freeform prompt string을
넘길 수 있는 parameter가 없다. 따라서 이 interface를 통해서는 privacy contract 위반을
표현할 수 없으며, 단순히 "잊을 수 있는 policy"가 아니다.

real LLM provider가 선택될 때까지 fake_llm.py가 유일한 implementation을 제공한다
(assistant_decisions.md "fake_llm 계약"). Job code는 concrete provider client가 아니라
get_llm()/set_llm()을 통해 이 abstract type에 의존한다.
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
    """metadata-only 평가.

    여기의 어떤 method도 raw message body나 freeform prompt string을 받지 않는다.
    module docstring 참고.
    """

    @abstractmethod
    def summarize(self, payload: SummaryInput) -> SummaryOutcome:
        """허용된 metadata field만으로 짧은 summary를 생성한다."""

    @abstractmethod
    def classify_importance(self, payload: ImportanceInput) -> ImportanceOutcome:
        """허용된 metadata field만으로 importance band + reason을 생성한다."""

    @abstractmethod
    def assess_cleanup(self, signal: CleanupSignal) -> CleanupAssessment:
        """read/archive/label state만으로 cleanup candidate의 confidence band와
        proposed action이 있으면 함께 생성한다."""


_active_llm: AssistantLLMPort | None = None


def set_llm(llm: AssistantLLMPort | None) -> None:
    """service-locator hook이며 mail_intake.gmail_reader.set_reader()와 같은 패턴이다.

    test는 test마다 fresh FakeAssistantLLM을 inject하고 teardown에서 None으로 reset한다.
    default(아무것도 설정되지 않음)는 fresh FakeAssistantLLM()이다.
    """
    global _active_llm
    _active_llm = llm


def get_llm() -> AssistantLLMPort:
    global _active_llm
    if _active_llm is None:
        from app.domains.assistant_decisions.fake_llm import FakeAssistantLLM

        _active_llm = FakeAssistantLLM()
    return _active_llm
