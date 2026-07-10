import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import metadata

# --- 0004_mail_intake_snapshot migration 영역 ---

gmail_messages = Table(
    "gmail_messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
    ),
    Column("gmail_message_id", String, nullable=False),
    Column("gmail_thread_id", String, nullable=False),
    Column("subject", String, nullable=True),
    Column("sender", String, nullable=True),
    Column("snippet", String, nullable=True),
    Column("received_at", DateTime(timezone=True), nullable=True),
    Column("is_read", Boolean, nullable=False, server_default="false"),
    Column("is_archived", Boolean, nullable=False, server_default="false"),
    Column("last_history_id", BigInteger, nullable=True),
    Column("snapshot_version", Integer, nullable=False, server_default="0"),
    UniqueConstraint(
        "connected_account_id",
        "gmail_message_id",
        name="uq_gmail_messages_account_message",
    ),
)

message_excerpts = Table(
    "message_excerpts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "message_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_messages.id"),
        nullable=False,
        unique=True,
    ),
    Column("excerpt_text", String, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

gmail_message_labels = Table(
    "gmail_message_labels",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "message_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_messages.id"),
        nullable=False,
    ),
    Column("gmail_label_id", String, nullable=False),
    Column("label_name", String, nullable=False),
    UniqueConstraint(
        "message_id", "gmail_label_id", name="uq_gmail_message_labels_message_label"
    ),
)

# --- 0005_mail_intake_sync migration 영역 ---

gmail_sync_cursors = Table(
    "gmail_sync_cursors",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
        unique=True,
    ),
    Column("last_history_id", BigInteger, nullable=True),
    Column("watch_expiration_at", DateTime(timezone=True), nullable=True),
    Column("last_successful_sync_at", DateTime(timezone=True), nullable=True),
    Column("cursor_status", String, nullable=False, server_default="valid"),
)

gmail_watch_registrations = Table(
    "gmail_watch_registrations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
    ),
    Column("topic_name", String, nullable=False),
    Column("expiration", DateTime(timezone=True), nullable=False),
    Column("status", String, nullable=False, server_default="active"),
)

gmail_notification_events = Table(
    "gmail_notification_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("email_address", String, nullable=False),
    Column("history_id", BigInteger, nullable=False),
    Column("dedupe_key", String, nullable=False, unique=True),
    Column("processed_at", DateTime(timezone=True), nullable=True),
)

sync_runs = Table(
    "sync_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
    ),
    Column("run_type", String, nullable=False),
    Column("trigger", String, nullable=False),
    Column("status", String, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("messages_changed_count", Integer, nullable=False, server_default="0"),
    Column("error_reason", String, nullable=True),
)
