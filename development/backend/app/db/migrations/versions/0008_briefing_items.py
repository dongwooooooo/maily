"""briefing: briefing_items (재생성 가능한 projection)

Revision ID: 0008_briefing_items
Revises: 0007_gmail_actions
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Alembic이 사용하는 revision 식별자.
revision = "0008_briefing_items"
down_revision = "0007_gmail_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "briefing_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
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
            nullable=False,
        ),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("importance_band", sa.String(), nullable=True),
        sa.Column("summary_text", sa.String(), nullable=True),
        sa.Column("rebuilt_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connected_account_id", "message_id", name="uq_briefing_items_account_message"
        ),
    )


def downgrade() -> None:
    op.drop_table("briefing_items")
