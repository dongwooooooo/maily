"""Read API service layer — docs/goals/backend-plans/briefing.md "Read API".

`GET /briefing/today`, `GET /messages/{id}`, `GET /storage/upcoming`. Kept
separate from service.py (which only owns the `rebuild_briefing` write
command) because this module is pure read/projection-shaping — no writes,
no events.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import NotFoundError, ValidationError
from app.domains.briefing import repository
from app.domains.briefing.schemas import (
    AccountBriefingGroup,
    BriefingCard,
    MessageDetail,
    UpcomingReminderEntry,
    UpcomingStorage,
)

_GMAIL_URL_TEMPLATE = "https://mail.google.com/mail/u/0/#all/{gmail_message_id}"


def _card_from_row(row: dict) -> BriefingCard:
    return BriefingCard(
        id=row["id"],
        connected_account_id=row["connected_account_id"],
        message_id=row["message_id"],
        section=row["section"],
        subject=row["subject"],
        sender=row["sender"],
        snippet=row["snippet"],
        received_at=row["received_at"],
        importance_band=row["importance_band"],
        summary_text=row["summary_text"],
        done=bool(row["is_read"]),
        seen=row["seen"],
        rebuilt_at=row["rebuilt_at"],
    )


async def get_today_briefing(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, scope: str
) -> list[AccountBriefingGroup]:
    """`GET /briefing/today?scope=all|{source_id}`.

    briefing_enabled=false accounts are excluded from the response
    entirely (briefing.md §필터). seen items are still included — seen is
    a flag on the card, not a filter (§필터: "제외가 아니라 seen 플래그로
    전달").
    """
    source_id = None
    if scope != "all":
        try:
            source_id = uuid.UUID(scope)
        except ValueError as exc:
            raise ValidationError("scope는 'all' 또는 유효한 source_id여야 합니다") from exc

    accounts = await repository.list_connected_accounts_for_workspace(
        connection, workspace_id=workspace_id, source_id=source_id
    )
    groups: list[AccountBriefingGroup] = []
    for account in accounts:
        if not account["briefing_enabled"]:
            continue
        rows = await repository.list_briefing_cards_for_account(
            connection, connected_account_id=account["id"]
        )
        groups.append(
            AccountBriefingGroup(
                connected_account_id=account["id"],
                gmail_address=account["gmail_address"],
                status=account["status"],
                syncing=account["status"] == "syncing",
                items=[_card_from_row(row) for row in rows],
            )
        )
    return groups


async def get_message_detail(
    connection: AsyncConnection, *, message_id: uuid.UUID, workspace_id: uuid.UUID
) -> MessageDetail:
    """`GET /messages/{id}` — readonly, no mutation action, no reason by
    default (briefing.md §negative). Cross-workspace lookups return 404,
    not 403, so existence isn't revealed (§권한)."""
    message = await repository.get_message(connection, message_id=message_id)
    if message is None:
        raise NotFoundError("message not found")

    account = await repository.get_connected_account(
        connection, connected_account_id=message["connected_account_id"]
    )
    if account is None or account["workspace_id"] != workspace_id:
        raise NotFoundError("message not found")

    excerpt = await repository.get_message_excerpt(connection, message_id=message_id)
    item = await repository.get_briefing_item_by_account_message(
        connection, connected_account_id=account["id"], message_id=message_id
    )

    return MessageDetail(
        id=message["id"],
        connected_account_id=account["id"],
        gmail_message_id=message["gmail_message_id"],
        gmail_thread_id=message["gmail_thread_id"],
        gmail_url=_GMAIL_URL_TEMPLATE.format(gmail_message_id=message["gmail_message_id"]),
        subject=message["subject"],
        sender=message["sender"],
        received_at=message["received_at"],
        excerpt_text=excerpt["excerpt_text"] if excerpt is not None else None,
        summary_text=item["summary_text"] if item is not None else None,
        importance_band=item["importance_band"] if item is not None else None,
        done=bool(message["is_read"]),
    )


def _week_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Monday 00:00 .. next Monday 00:00 in `now`'s tzinfo — "이번주"
    boundary. briefing.md says this should be the user's timezone; no
    per-user timezone field exists yet anywhere in the schema, so this
    worktree uses the server/request tz passed in as `now` (UTC by
    default) — flagged as an open question for the coordinator."""
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = start_of_day - timedelta(days=start_of_day.weekday())
    next_monday = monday + timedelta(days=7)
    return monday, next_monday


async def get_storage_upcoming(
    connection: AsyncConnection, *, workspace_id: uuid.UUID, now: datetime | None = None
) -> UpcomingStorage:
    """`GET /storage/upcoming` — pending reminders only (§필터), grouped
    into today/tomorrow/this_week ascending by remind_at. A reactivated
    reminder is never returned here — repository.list_pending_reminders_for_workspace
    already filters to status='pending' (§negative)."""
    now = now or datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    day_after_tomorrow = tomorrow_start + timedelta(days=1)
    _week_start, week_end = _week_bounds(now)

    rows = await repository.list_pending_reminders_for_workspace(
        connection, workspace_id=workspace_id
    )

    today: list[UpcomingReminderEntry] = []
    tomorrow: list[UpcomingReminderEntry] = []
    this_week: list[UpcomingReminderEntry] = []
    for row in rows:
        entry = UpcomingReminderEntry(
            reminder_id=row["reminder_id"], message_id=row["message_id"], remind_at=row["remind_at"]
        )
        if today_start <= entry.remind_at < tomorrow_start:
            today.append(entry)
        elif tomorrow_start <= entry.remind_at < day_after_tomorrow:
            tomorrow.append(entry)
        elif day_after_tomorrow <= entry.remind_at < week_end:
            this_week.append(entry)
        else:
            # beyond this calendar week — still "앞으로 다시 볼 예정"
            # (§negative rules out only *past* reactivated reminders, not
            # far-future ones), so it still belongs in storage. No further
            # bucket is specified, so it's folded into this_week.
            this_week.append(entry)

    return UpcomingStorage(today=today, tomorrow=tomorrow, this_week=this_week)
