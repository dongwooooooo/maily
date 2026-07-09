"""notifications: notification_subscriptions, notification_events

Revision ID: 0012_notifications
Revises: 0011_assistant_rules
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0012_notifications"
down_revision = "0011_assistant_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("keys", postgresql.JSONB(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("endpoint", name="uq_notification_subscriptions_endpoint"),
    )

    op.create_table(
        "notification_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("notification_type", sa.String(), nullable=False),
        sa.Column("route_target", postgresql.JSONB(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        # Not in db-schema.md's notifications table (only id/workspace_id/
        # notification_type/route_target/read_at are listed there) — added
        # because the Read API's documented "최신순" (most-recent-first)
        # ordering requirement (notifications.md "GET /notifications
        # [필터]") needs a creation timestamp to order by. Mirrors
        # outbox_events.created_at (app/core/outbox.py), not a status enum
        # column, so it does not touch _integration-contract.md §5.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index(
            "ix_notification_events_workspace_id_created_at",
            "workspace_id",
            "created_at",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_events")
    op.drop_table("notification_subscriptions")
