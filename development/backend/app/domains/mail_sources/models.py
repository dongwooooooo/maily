import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import metadata

connected_gmail_accounts = Table(
    "connected_gmail_accounts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column("gmail_address", String, nullable=False),
    Column("display_name", String, nullable=True),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False, server_default="0"),
    Column("connected_at", DateTime(timezone=True), nullable=False),
    Column("disconnected_at", DateTime(timezone=True), nullable=True),
    Index(
        "uq_connected_gmail_accounts_active_workspace_address",
        "workspace_id",
        "gmail_address",
        unique=True,
        postgresql_where=text("status <> 'disconnected'"),
    ),
)

gmail_oauth_credentials = Table(
    "gmail_oauth_credentials",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
        unique=True,
    ),
    Column("access_token_ciphertext", LargeBinary, nullable=False),
    Column("refresh_token_ciphertext", LargeBinary, nullable=False),
    Column("encryption_key_version", Integer, nullable=False),
    Column("scope", String, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)

gmail_source_settings = Table(
    "gmail_source_settings",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
        unique=True,
    ),
    Column("briefing_enabled", Boolean, nullable=False, server_default="true"),
    Column("summary_enabled", Boolean, nullable=False, server_default="true"),
    Column("notification_enabled", Boolean, nullable=False, server_default="true"),
    Column("paused", Boolean, nullable=False, server_default="false"),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
