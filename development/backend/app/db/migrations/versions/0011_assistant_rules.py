"""assistant_decisions: classification_rules, rule_suggestions, cleanup_proposals

Revision ID: 0011_assistant_rules
Revises: 0010_assistant_eval
Create Date: 2026-07-09

`rule_suggestions`는 `label_correction_signals`(labels, 0006)를 reference하고
`cleanup_proposals`는 `gmail_action_commands`(gmail_actions, 0007)를 reference한다.
둘 다 이미 이 worktree에 merge되어 있으므로 두 FK는 local에서 resolve된다.
down_revision placeholder에 대해서는 0010_assistant_eval.py의 note 참고. 이 file의
down_revision은 `0010_assistant_eval` 그대로 유지한다(chain의 root placeholder만
coordinator repointing이 필요).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Alembic이 사용하는 revision 식별자.
revision = "0011_assistant_rules"
down_revision = "0010_assistant_eval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classification_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "service_label_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_labels.id"),
            nullable=False,
        ),
        sa.Column("match_condition", postgresql.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "rule_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "correction_signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("label_correction_signals.id"),
            nullable=False,
        ),
        sa.Column("suggested_condition", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "cleanup_proposals",
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
        ),
        sa.Column("proposed_action", sa.String(), nullable=False),
        sa.Column("confidence_band", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("before_state", postgresql.JSONB(), nullable=False),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column(
            "gmail_action_command_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gmail_action_commands.id"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cleanup_proposals")
    op.drop_table("rule_suggestions")
    op.drop_table("classification_rules")
