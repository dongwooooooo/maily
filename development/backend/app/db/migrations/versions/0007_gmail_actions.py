"""gmail_actions: gmail_action_commands, activity_logs, undo_actions

Revision ID: 0007_gmail_actions
Revises: 0006_labels
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007_gmail_actions"
down_revision = "0006_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_action_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=True,
        ),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed", sa.Boolean(), nullable=True),
        sa.Column(
            "requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_reason", sa.String(), nullable=True),
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "command_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_action_commands.id"),
            nullable=True,
        ),
        sa.Column("action_summary", sa.String(), nullable=False),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "undo_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activity_logs.id"),
            nullable=False,
        ),
        sa.Column(
            "original_command_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_action_commands.id"),
            nullable=False,
        ),
        sa.Column(
            "reverse_command_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_action_commands.id"),
            nullable=True,
        ),
        sa.Column("undo_available", sa.Boolean(), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("undo_actions")
    op.drop_table("activity_logs")
    op.drop_table("gmail_action_commands")
