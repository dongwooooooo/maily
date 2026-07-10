"""GmailReaderPort: mail_intake가 Gmail data를 읽는 유일한 방법.

module-boundaries.md invariant: "Gmail read/sync 호출은 mail_intake의
GmailReaderPort ... 를 통해서만 한다." repository/service/job code는 concrete Gmail SDK
client가 아니라 이 abstract type에 의존해야 한다.

모든 method는 `connected_account_id`만 받고 raw OAuth token은 절대 받지 않는다.
implementation은 mail_sources가 inject하는 handle을 통해 credential을 resolve한다
(live_reader.py 참고). 여기의 어떤 method도 Gmail message body를 반환하면 안 된다. 반환되는
유일한 text field는 Gmail의 짧은 `snippet`(`messages.get(format=metadata)`에 이미 포함되는
값)이며, `format=full` content가 아니다. 각 method가 만족해야 하는 전체 behavioral contract는
mail_intake.md "Port 계약" 참고.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypedDict


class HistoryRecord(TypedDict):
    record_type: str  # "message_added" | "message_deleted" | "labels_added" | "labels_removed"
    gmail_message_id: str
    label_ids: list[str]


class HistoryResult(TypedDict):
    records: list[HistoryRecord]
    new_history_id: int
    valid: bool


class MessageMetadata(TypedDict):
    subject: str | None
    sender: str | None
    snippet: str | None
    thread_id: str
    label_ids: list[str]
    is_read: bool
    is_archived: bool
    received_at: datetime | None


class WatchRegistration(TypedDict):
    topic_name: str
    expiration: datetime
    history_id: int


class MessageIdList(TypedDict):
    gmail_message_id: list[str]
    history_id: int


class GmailAuthError(Exception):
    """Gmail이 credential을 거부할 때 reader implementation이 raise한다.

    401/403, scope reduction 등이 해당한다. caller(service/job code)는 이를 generic sync
    failure로 처리하지 않고 `gmail_source_recovery_needed`를 emit하기 위해 구체적으로 catch한다.
    mail_intake는 account status를 직접 write하지 않는다(그 소유권은 mail_sources에 유지).
    """

    def __init__(self, message: str, *, reason: str = "auth_error"):
        super().__init__(message)
        self.reason = reason


class GmailReaderPort(ABC):
    """Gmail에 대한 read/sync-only access.

    여기에는 mutation method가 없다. write access는 다른 domain이 소유한 별도 port인
    `gmail_actions`의 `GmailMutationPort`다.
    """

    @abstractmethod
    async def register_watch(self, connected_account_id: uuid.UUID) -> WatchRegistration:
        """이 account의 Pub/Sub watch를 register 또는 re-register한다."""

    @abstractmethod
    async def history(
        self, connected_account_id: uuid.UUID, start_history_id: int | None
    ) -> HistoryResult:
        """`start_history_id` 이후의 history record를 나열한다.

        `valid=False`는 Gmail이 `start_history_id`를 더 이상 인식하지 못한다는 뜻이다(너무
        오래됐거나 본 적 없음). caller는 delta를 retry하지 말고 full resync로 promote해야 한다.
        """

    @abstractmethod
    async def get_message_metadata(
        self, connected_account_id: uuid.UUID, gmail_message_id: str
    ) -> MessageMetadata:
        """metadata-only message data를 fetch한다(`messages.get(format=metadata)` shape).

        full message body를 fetch하거나 반환하면 안 된다.
        """

    @abstractmethod
    async def list_message_ids(self, connected_account_id: uuid.UUID) -> MessageIdList:
        """mailbox에 현재 있는 모든 message id를 enumerate한다.

        full resync의 input이다.
        """


_active_reader: GmailReaderPort | None = None


def set_reader(reader: GmailReaderPort | None) -> None:
    """job/service code가 concrete implementation을 직접 import하지 않고 `get_reader()`를
    호출하게 하는 service-locator hook이다.

    이를 통해 code는 abstract port에만 의존한다. test는 job handler 호출 전에 seeded
    `FakeGmailReader`를 inject하려고 이 함수를 호출하고, teardown에서 `None`으로 reset해야 한다.
    Task 4/5 범위에는 live wiring이 없다. default(아무것도 설정하지 않은 첫 read)는 fresh
    `FakeGmailReader()`다.
    """
    global _active_reader
    _active_reader = reader


def get_reader() -> GmailReaderPort:
    global _active_reader
    if _active_reader is None:
        from app.domains.mail_intake.fake_reader import FakeGmailReader

        _active_reader = FakeGmailReader()
    return _active_reader
