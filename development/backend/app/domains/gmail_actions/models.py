import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import metadata

gmail_action_commands = Table(
    "gmail_action_commands",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
    ),
    Column("message_id", UUID(as_uuid=True), ForeignKey("gmail_messages.id"), nullable=True),
    Column("action_type", String, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("idempotency_key", String, nullable=False, unique=True),
    Column("status", String, nullable=False, server_default="pending"),
    Column("version", Integer, nullable=False, server_default="0"),
    Column("changed", Boolean, nullable=True),
    Column("requested_by", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=True),
    Column("failed_at", DateTime(timezone=True), nullable=True),
    Column("error_reason", String, nullable=True),
)

activity_logs = Table(
    "activity_logs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column(
        "command_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_action_commands.id"),
        nullable=True,
    ),
    Column("action_summary", String, nullable=False),
    Column("actor_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

undo_actions = Table(
    "undo_actions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("activity_id", UUID(as_uuid=True), ForeignKey("activity_logs.id"), nullable=False),
    Column(
        "original_command_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_action_commands.id"),
        nullable=False,
    ),
    Column(
        "reverse_command_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_action_commands.id"),
        nullable=True,
    ),
    Column("undo_available", Boolean, nullable=False),
    Column("undone_at", DateTime(timezone=True), nullable=True),
)
