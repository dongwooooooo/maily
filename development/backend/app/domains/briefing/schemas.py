import uuid
from datetime import datetime

from pydantic import BaseModel

# section value set is [미정] — db-schema.md "briefing_items.section" /
# _integration-contract.md §5. Until product-wireframe-final.md's card
# section table is confirmed, every projected item is placed in this single
# fake_section contract constant (docs/goals/backend-plans/briefing.md
# "워크트리 격리 노트"). Do not invent additional section values here.
FAKE_SECTION = "fake_section"

# reminders.status enum — fixed by _integration-contract.md §5.
REMINDER_STATUSES = {"pending", "reactivated", "cancelled"}


class BriefingCard(BaseModel):
    """Today-briefing / card list shape.

    Deliberately excludes any Gmail mutation action, AI judgement reason,
    or raw body field — briefing.md "카드 응답에는 Gmail mutation action,
    AI 판단 이유, raw body를 넣지 않는다" (강제 invariant). Tests assert
    field *absence*, not null values, so no such field is declared here.
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

    No mutation action field (mark_read/archive/label) and no AI reason
    field by default — briefing.md "Read API" §negative / §빈상태.
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
