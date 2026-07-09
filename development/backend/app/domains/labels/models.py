import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import metadata

service_labels = Table(
    "service_labels",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column("name", String, nullable=False),
    Column("order_index", Integer, nullable=False),
    Column("hidden", Boolean, nullable=False, server_default="false"),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "name", name="uq_service_labels_workspace_id_name"),
)

gmail_label_mappings = Table(
    "gmail_label_mappings",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "service_label_id",
        UUID(as_uuid=True),
        ForeignKey("service_labels.id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "connected_account_id",
        UUID(as_uuid=True),
        ForeignKey("connected_gmail_accounts.id"),
        nullable=False,
    ),
    # Null until gmail_actions actually creates the label in Gmail — see
    # docs/goals/backend-plans/labels.md "매핑 분리 근거".
    Column("gmail_label_id", String, nullable=True),
    Column("gmail_label_name", String, nullable=False),
)

label_correction_signals = Table(
    "label_correction_signals",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("message_id", UUID(as_uuid=True), ForeignKey("gmail_messages.id"), nullable=False),
    Column(
        "service_label_id", UUID(as_uuid=True), ForeignKey("service_labels.id"), nullable=False
    ),
    Column("actor_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False),
)
