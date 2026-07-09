"""assistant_decisions: summary_jobs, message_summaries, importance_jobs,
message_importance_classifications

Revision ID: 0010_assistant_eval
Revises: 0009_briefing_state
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0010_assistant_eval"
down_revision = "0009_briefing_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summary_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "message_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary_text", sa.String(), nullable=True),
        sa.Column("is_metadata_only", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("summary_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_name", sa.String(), nullable=True),
    )

    op.create_table(
        "importance_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "message_importance_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_messages.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("importance_band", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("classification_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("message_importance_classifications")
    op.drop_table("importance_jobs")
    op.drop_table("message_summaries")
    op.drop_table("summary_jobs")
