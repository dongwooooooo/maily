"""briefing: briefing_item_states (durable), reminders

Revision ID: 0009_briefing_state
Revises: 0008_briefing_items
Create Date: 2026-07-09

COORDINATOR NOTE: `briefing_item_states.version` is not listed in
docs/areas/backend/db-schema.md's column table for this table — added
here because docs/goals/backend-plans/briefing.md's set_item_seen /
schedule_reminder checklists require a monotonic version to build the
outbox idempotency key `item:{id}:state:{version}` and to detect no-op
updates. Please fold this column back into db-schema.md.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0009_briefing_state"
down_revision = "0008_briefing_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "briefing_item_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("seen", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remind_later_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "briefing_item_state_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("briefing_item_states.id"),
            nullable=False,
        ),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
    )


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("briefing_item_states")
