"""mail_intake: gmail_sync_cursors, gmail_watch_registrations, gmail_notification_events, sync_runs

Revision ID: 0005_mail_intake_sync
Revises: 0004_mail_intake_snapshot
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_mail_intake_sync"
down_revision = "0004_mail_intake_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_sync_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("last_history_id", sa.BigInteger(), nullable=True),
        sa.Column("watch_expiration_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_status", sa.String(), nullable=False, server_default="valid"),
    )

    op.create_table(
        "gmail_watch_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
        ),
        sa.Column("topic_name", sa.String(), nullable=False),
        sa.Column("expiration", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )

    op.create_table(
        "gmail_notification_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email_address", sa.String(), nullable=False),
        sa.Column("history_id", sa.BigInteger(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False, unique=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
        ),
        sa.Column("run_type", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_changed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_reason", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_table("gmail_notification_events")
    op.drop_table("gmail_watch_registrations")
    op.drop_table("gmail_sync_cursors")
