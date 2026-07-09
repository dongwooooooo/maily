import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import metadata

# --- 0008_briefing_items ---

briefing_items = Table(
    "briefing_items",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
    ),
    Column("message_id", UUID(as_uuid=True), ForeignKey("gmail_messages.id"), nullable=False),
    Column("section", String, nullable=False),
    Column("importance_band", String, nullable=True),
    Column("summary_text", String, nullable=True),
    Column("rebuilt_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "connected_account_id", "message_id", name="uq_briefing_items_account_message"
    ),
)

# --- 0009_briefing_state ---

briefing_item_states = Table(
    "briefing_item_states",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column(
        "message_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_messages.id"),
        nullable=False,
        unique=True,
    ),
    Column("seen", Boolean, nullable=False, server_default="false"),
    Column("seen_at", DateTime(timezone=True), nullable=True),
    Column("remind_later_at", DateTime(timezone=True), nullable=True),
    # NOTE: not listed in docs/areas/backend/db-schema.md's
    # briefing_item_states column table — added because
    # docs/goals/backend-plans/briefing.md's set_item_seen/schedule_reminder
    # checklists require a monotonic version to build the
    # `item:{id}:state:{version}` outbox idempotency key and to make a
    # no-op update distinguishable from a real change ([멱등] checklist
    # entries). Flagged for the coordinator to fold back into db-schema.md.
    Column("version", Integer, nullable=False, server_default="0"),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

reminders = Table(
    "reminders",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "briefing_item_state_id",
        UUID(as_uuid=True),
        ForeignKey("briefing_item_states.id"),
        nullable=False,
    ),
    Column("remind_at", DateTime(timezone=True), nullable=False),
    Column("reactivated_at", DateTime(timezone=True), nullable=True),
    Column("status", String, nullable=False, server_default="pending"),
)
