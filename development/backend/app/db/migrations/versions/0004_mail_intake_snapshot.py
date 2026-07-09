"""mail_intake: gmail_messages, message_excerpts, gmail_message_labels

Revision ID: 0004_mail_intake_snapshot
Revises: 0003_mail_sources
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_mail_intake_snapshot"
down_revision = "0003_mail_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gmail_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
        ),
        sa.Column("gmail_message_id", sa.String(), nullable=False),
        sa.Column("gmail_thread_id", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("sender", sa.String(), nullable=True),
        sa.Column("snippet", sa.String(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_history_id", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_unique_constraint(
        "uq_gmail_messages_account_message",
        "gmail_messages",
        ["connected_account_id", "gmail_message_id"],
    )

    op.create_table(
        "message_excerpts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("excerpt_text", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "gmail_message_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
        ),
        sa.Column("gmail_label_id", sa.String(), nullable=False),
        sa.Column("label_name", sa.String(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_gmail_message_labels_message_label",
        "gmail_message_labels",
        ["message_id", "gmail_label_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_gmail_message_labels_message_label",
        "gmail_message_labels",
        type_="unique",
    )
    op.drop_table("gmail_message_labels")
    op.drop_table("message_excerpts")
    op.drop_constraint(
        "uq_gmail_messages_account_message", "gmail_messages", type_="unique"
    )
    op.drop_table("gmail_messages")
