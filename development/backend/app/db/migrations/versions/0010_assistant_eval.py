"""assistant_decisions: summary_jobs, message_summaries, importance_jobs,
message_importance_classifications

Revision ID: 0010_assistant_eval
Revises: 0007_gmail_actions
Create Date: 2026-07-09

NOTE (worktree isolation): _integration-contract.md §1 assigns this
revision's down_revision as `0009_briefing_state` (after briefing's two
migrations). This worktree only has `0007_gmail_actions` merged locally —
briefing (0008/0009) is being built in a sibling worktree and isn't visible
here. down_revision is pointed at `0007_gmail_actions` as a placeholder;
the coordinator must repoint it to `0009_briefing_state` at merge time
per the documented chain order. revision/down_revision slugs otherwise
match the contract table exactly (no autogenerate).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0010_assistant_eval"
down_revision = "0007_gmail_actions"  # placeholder — coordinator repoints to 0009_briefing_state
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
