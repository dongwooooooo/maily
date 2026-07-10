import uuid
from datetime import datetime

from pydantic import BaseModel

# section value set은 [미정]이다 — db-schema.md "briefing_items.section" /
# _integration-contract.md §5. product-wireframe-final.md의 card section table이 확정될
# 때까지 모든 projected item은 이 단일 fake_section contract constant에 둔다
# (docs/goals/backend-plans/briefing.md "워크트리 격리 노트"). 여기서 추가 section value를
# 만들지 않는다.
FAKE_SECTION = "fake_section"

# reminders.status enum은 _integration-contract.md §5로 고정된다.
REMINDER_STATUSES = {"pending", "reactivated", "cancelled"}


class BriefingCard(BaseModel):
    """today briefing / card list shape.

    Gmail mutation action, AI judgement reason, raw body field를 의도적으로 제외한다.
    briefing.md "카드 응답에는 Gmail mutation action, AI 판단 이유, raw body를 넣지 않는다"
    (강제 invariant). test는 null value가 아니라 field *absence*를 assert하므로, 그런 field를
    여기 선언하지 않는다.
    """

    id: uuid.UUID
    connected_account_id: uuid.UUID
    message_id: uuid.UUID
    section: str
    subject: str | None
    sender: str | None
    snippet: str | None
    received_at: datetime | None
    importance_band: str | None
    summary_text: str | None
    done: bool
    seen: bool
    rebuilt_at: datetime


class AccountBriefingGroup(BaseModel):
    connected_account_id: uuid.UUID
    gmail_address: str
    status: str
    syncing: bool
    items: list[BriefingCard]


class MessageDetail(BaseModel):
    """GET /messages/{id} readonly view.

    mutation action field(mark_read/archive/label)가 없고 AI reason field도 기본으로 없다.
    briefing.md "Read API" §negative / §빈상태 기준이다.
    """

    id: uuid.UUID
    connected_account_id: uuid.UUID
    gmail_message_id: str
    gmail_thread_id: str
    gmail_url: str
    subject: str | None
    sender: str | None
    received_at: datetime | None
    excerpt_text: str | None
    summary_text: str | None
    importance_band: str | None
    done: bool


class ItemStateResult(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    message_id: uuid.UUID
    seen: bool
    seen_at: datetime | None
    remind_later_at: datetime | None
    version: int
    updated_at: datetime


class ReminderResult(BaseModel):
    id: uuid.UUID
    briefing_item_state_id: uuid.UUID
    remind_at: datetime
    reactivated_at: datetime | None
    status: str


class UpcomingReminderEntry(BaseModel):
    reminder_id: uuid.UUID
    message_id: uuid.UUID
    remind_at: datetime


class UpcomingStorage(BaseModel):
    today: list[UpcomingReminderEntry]
    tomorrow: list[UpcomingReminderEntry]
    this_week: list[UpcomingReminderEntry]
