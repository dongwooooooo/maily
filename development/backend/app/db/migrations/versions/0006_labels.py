"""labels: service_labels, gmail_label_mappings, label_correction_signals

Revision ID: 0006_labels
Revises: 0005_mail_intake_sync
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006_labels"
down_revision = "0005_mail_intake_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "name", name="uq_service_labels_workspace_id_name"
        ),
    )

    op.create_table(
        "gmail_label_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "service_label_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_labels.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
        ),
        sa.Column("gmail_label_id", sa.String(), nullable=True),
        sa.Column("gmail_label_name", sa.String(), nullable=False),
    )

    op.create_table(
        "label_correction_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
        ),
        sa.Column(
            "service_label_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_labels.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("label_correction_signals")
    op.drop_table("gmail_label_mappings")
    op.drop_table("service_labels")
