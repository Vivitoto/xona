"""Create durable job tables.

Revision ID: 0008_jobs
Revises: 0007_actors
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_jobs"
down_revision: Union[str, None] = "0007_actors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(length=255), nullable=True),
        sa.Column("media_identity", sa.String(length=255), nullable=False),
        sa.Column("manual", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(
        "ix_jobs_active_rule_media",
        "jobs",
        ["rule_id", "media_identity", "state"],
    )
    op.create_index(
        "ix_jobs_active_manual_media",
        "jobs",
        ["manual", "media_identity", "state"],
    )
    op.create_index(
        "ix_jobs_lease",
        "jobs",
        ["state", "next_run_at", "lease_expires_at"],
    )
    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(length=64), nullable=True),
        sa.Column("to_state", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_events_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_events")),
    )


def downgrade() -> None:
    op.drop_table("job_events")
    op.drop_index("ix_jobs_lease", table_name="jobs")
    op.drop_index("ix_jobs_active_manual_media", table_name="jobs")
    op.drop_index("ix_jobs_active_rule_media", table_name="jobs")
    op.drop_table("jobs")
