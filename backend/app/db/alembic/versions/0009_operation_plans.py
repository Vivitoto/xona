"""Create immutable operation plan tables.

Revision ID: 0009_operation_plans
Revises: 0008_jobs
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_operation_plans"
down_revision: Union[str, None] = "0008_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operation_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column("plan_json", sa.JSON(), nullable=False),
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
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_operation_plans_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operation_plans")),
        sa.UniqueConstraint("plan_id", name="uq_operation_plans_plan_id"),
    )
    op.create_index(
        "ix_operation_plans_job_created",
        "operation_plans",
        ["job_id", "created_at"],
    )
    op.create_table(
        "operation_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_plan_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(length=96), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("target_path", sa.Text(), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column("step_json", sa.JSON(), nullable=False),
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
            ["operation_plan_id"],
            ["operation_plans.id"],
            name=op.f("fk_operation_steps_operation_plan_id_operation_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operation_steps")),
        sa.UniqueConstraint(
            "operation_plan_id",
            "step_id",
            name="uq_operation_steps_plan_step",
        ),
    )
    op.create_index(
        "ix_operation_steps_plan_sequence",
        "operation_steps",
        ["operation_plan_id", "sequence"],
    )
    op.create_index(
        "ix_operation_steps_target_path",
        "operation_steps",
        ["target_path"],
    )


def downgrade() -> None:
    op.drop_index("ix_operation_steps_target_path", table_name="operation_steps")
    op.drop_index("ix_operation_steps_plan_sequence", table_name="operation_steps")
    op.drop_table("operation_steps")
    op.drop_index("ix_operation_plans_job_created", table_name="operation_plans")
    op.drop_table("operation_plans")
