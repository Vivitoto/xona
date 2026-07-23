"""Create watch rules and durable monitor state.

Revision ID: 0010_watch_monitor_state
Revises: 0009_operation_plans
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_watch_monitor_state"
down_revision: Union[str, None] = "0009_operation_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE_JOB_PREDICATE = (
    "state NOT IN ('completed', 'failed', 'cancelled', 'rolled_back')"
)


def upgrade() -> None:
    op.create_table(
        "watch_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("source_directory", sa.Text(), nullable=False),
        sa.Column("destination_directory", sa.Text(), nullable=False),
        sa.Column("recursive", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("realtime", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "polling_interval_seconds",
            sa.Integer(),
            server_default=sa.text("60"),
            nullable=False,
        ),
        sa.Column(
            "stability_seconds",
            sa.Integer(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "stable_check_count",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
        sa.Column("organization_mode", sa.String(length=32), nullable=False),
        sa.Column("folder_templates", sa.JSON(), nullable=False),
        sa.Column("filename_template", sa.Text(), nullable=False),
        sa.Column("asset_policy", sa.String(length=32), nullable=False),
        sa.Column("emby_options", sa.JSON(), nullable=False),
        sa.Column("metadata_options", sa.JSON(), nullable=False),
        sa.Column("include_patterns", sa.JSON(), nullable=False),
        sa.Column("exclude_patterns", sa.JSON(), nullable=False),
        sa.Column("excluded_destination_prefixes", sa.JSON(), nullable=False),
        sa.Column(
            "confidence_threshold",
            sa.Integer(),
            server_default=sa.text("92"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watch_rules")),
        sa.UniqueConstraint("rule_id", name="uq_watch_rules_rule_id"),
    )
    op.create_index(
        "ix_watch_rules_enabled",
        "watch_rules",
        ["enabled", "source_directory"],
    )
    op.create_table(
        "monitor_media_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("media_identity", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=True),
        sa.Column("stable_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_enqueued_job_id", sa.Integer(), nullable=True),
        sa.Column("terminal_state", sa.String(length=64), nullable=True),
        sa.Column("last_seen_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["watch_rules.rule_id"],
            name=op.f("fk_monitor_media_state_rule_id_watch_rules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_enqueued_job_id"],
            ["jobs.id"],
            name=op.f("fk_monitor_media_state_last_enqueued_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitor_media_state")),
    )
    op.create_index(
        "uq_monitor_media_state_rule_identity",
        "monitor_media_state",
        ["rule_id", "media_identity"],
        unique=True,
    )
    op.create_index(
        "uq_jobs_active_rule_media",
        "jobs",
        ["rule_id", "media_identity"],
        unique=True,
        sqlite_where=sa.text(
            "manual = 0 AND rule_id IS NOT NULL AND " + ACTIVE_JOB_PREDICATE
        ),
    )
    op.create_index(
        "uq_jobs_active_manual_media",
        "jobs",
        ["media_identity"],
        unique=True,
        sqlite_where=sa.text("manual = 1 AND " + ACTIVE_JOB_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_active_manual_media", table_name="jobs")
    op.drop_index("uq_jobs_active_rule_media", table_name="jobs")
    op.drop_index(
        "uq_monitor_media_state_rule_identity",
        table_name="monitor_media_state",
    )
    op.drop_table("monitor_media_state")
    op.drop_index("ix_watch_rules_enabled", table_name="watch_rules")
    op.drop_table("watch_rules")
