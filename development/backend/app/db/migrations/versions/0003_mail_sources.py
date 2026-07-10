"""mail_sources 테이블: connected_gmail_accounts, gmail_oauth_credentials, gmail_source_settings

Revision ID: 0003_mail_sources
Revises: 0002_identity
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Alembic이 사용하는 revision 식별자.
revision = "0003_mail_sources"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connected_gmail_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("gmail_address", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_connected_gmail_accounts_active_workspace_address",
        "connected_gmail_accounts",
        ["workspace_id", "gmail_address"],
        unique=True,
        postgresql_where=sa.text("status <> 'disconnected'"),
    )

    op.create_table(
        "gmail_oauth_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("access_token_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "gmail_source_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connected_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connected_gmail_accounts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("briefing_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("summary_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notification_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gmail_source_settings")
    op.drop_table("gmail_oauth_credentials")
    op.drop_index(
        "uq_connected_gmail_accounts_active_workspace_address",
        table_name="connected_gmail_accounts",
    )
    op.drop_table("connected_gmail_accounts")
