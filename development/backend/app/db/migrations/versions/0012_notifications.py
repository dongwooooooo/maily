"""notifications 테이블: notification_subscriptions, notification_events

Revision ID: 0012_notifications
Revises: 0011_assistant_rules
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Alembic이 사용하는 revision 식별자.
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
        # db-schema.md의 notifications table에는 없다(거기에는 id/workspace_id/
        # notification_type/route_target/read_at만 나열됨). Read API 문서의 "최신순"
        # 최신순(most-recent-first) ordering requirement(notifications.md
        # "GET /notifications [필터]")가 정렬용 creation timestamp를 필요로 하므로 추가했다.
        # status enum column이 아니라 outbox_events.created_at(app/core/outbox.py)을
        # mirror하므로 _integration-contract.md §5를 건드리지 않는다.
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
