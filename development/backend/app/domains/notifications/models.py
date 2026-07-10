import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import metadata

notification_subscriptions = Table(
    "notification_subscriptions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("endpoint", String, nullable=False),
    Column("keys", JSONB, nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("endpoint", name="uq_notification_subscriptions_endpoint"),
)

notification_events = Table(
    "notification_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column("notification_type", String, nullable=False),
    # generic-landing-prohibition invariant lives at the app layer
    # (service._require_route_target) — this column only enforces NOT NULL.
    Column("route_target", JSONB, nullable=False),
    Column("read_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index(
        "ix_notification_events_workspace_id_created_at",
        "workspace_id",
        "created_at",
    ),
)
