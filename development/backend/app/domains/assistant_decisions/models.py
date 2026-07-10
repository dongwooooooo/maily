import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import metadata

# --- 0010_assistant_eval migration 영역 ---

summary_jobs = Table(
    "summary_jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("message_id", UUID(as_uuid=True), ForeignKey("gmail_messages.id"), nullable=False),
    Column("status", String, nullable=False, server_default="queued"),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

message_summaries = Table(
    "message_summaries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "message_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_messages.id"),
        nullable=False,
        unique=True,
    ),
    # G6 privacy contract: 이 module 어디에도 body/prompt column은 없다. summary_text는
    # 짧은 derived string일 뿐이며 raw email content가 아니다. null summary_text +
    # is_metadata_only=True는 UI가 분기하는 "summary off / fallback" fingerprint다.
    Column("summary_text", String, nullable=True),
    Column("is_metadata_only", Boolean, nullable=False, server_default="false"),
    Column("summary_version", Integer, nullable=False, server_default="0"),
    Column("model_name", String, nullable=True),
)

importance_jobs = Table(
    "importance_jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("message_id", UUID(as_uuid=True), ForeignKey("gmail_messages.id"), nullable=False),
    Column("status", String, nullable=False, server_default="queued"),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

message_importance_classifications = Table(
    "message_importance_classifications",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "message_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_messages.id"),
        nullable=False,
        unique=True,
    ),
    Column("importance_band", String, nullable=False),
    # AI 판단 이유 — 기본 노출 안 함(최상위 원칙). 저장은 하되 공개 스키마에서 제외.
    Column("reason", String, nullable=False),
    Column("classification_version", Integer, nullable=False, server_default="0"),
)

# --- 0011_assistant_rules migration 영역 ---

classification_rules = Table(
    "classification_rules",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column(
        "service_label_id", UUID(as_uuid=True), ForeignKey("service_labels.id"), nullable=False
    ),
    Column("match_condition", JSONB, nullable=False),
    Column("active", Boolean, nullable=False, server_default="true"),
)

rule_suggestions = Table(
    "rule_suggestions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column(
        "correction_signal_id",
        UUID(as_uuid=True),
        ForeignKey("label_correction_signals.id"),
        nullable=False,
    ),
    Column("suggested_condition", JSONB, nullable=False),
    Column("status", String, nullable=False, server_default="pending"),
    Column("decided_at", DateTime(timezone=True), nullable=True),
)

cleanup_proposals = Table(
    "cleanup_proposals",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False),
    Column("message_id", UUID(as_uuid=True), ForeignKey("gmail_messages.id"), nullable=False),
    Column("proposed_action", String, nullable=False),
    Column("confidence_band", String, nullable=False),
    Column("status", String, nullable=False, server_default="pending"),
    # before/after는 label/read-state metadata preview일 뿐이며 raw body가 아니다.
    Column("before_state", JSONB, nullable=False),
    Column("after_state", JSONB, nullable=True),
    Column(
        "gmail_action_command_id",
        UUID(as_uuid=True),
        ForeignKey("gmail_action_commands.id"),
        nullable=True,
    ),
    Column("decided_at", DateTime(timezone=True), nullable=True),
)
