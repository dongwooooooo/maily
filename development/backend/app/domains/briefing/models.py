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
    # docs/areas/backend/db-schema.md documents this column — monotonic
    # version for the `item:{id}:state:{version}` outbox idempotency key
    # and no-op-update detection ([멱등] checklist entries).
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
