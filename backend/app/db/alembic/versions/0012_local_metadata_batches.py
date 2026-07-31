"""Create local metadata batch tables.

Revision ID: 0012_local_metadata_batches
Revises: 0011_emby_links
Create Date: 2026-07-31 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_local_metadata_batches"
down_revision: Union[str, None] = "0011_emby_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_metadata_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("total_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pending_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("running_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("executable_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("executed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "execute_failed_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_metadata_batches")),
        sa.UniqueConstraint(
            "batch_id",
            name="uq_local_metadata_batches_batch_id",
        ),
    )
    op.create_index(
        "ix_local_metadata_batches_status",
        "local_metadata_batches",
        ["status"],
    )
    op.create_index(
        "ix_local_metadata_batches_updated_at",
        "local_metadata_batches",
        ["updated_at"],
    )
    op.create_table(
        "local_metadata_batch_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("video_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=False),
        sa.Column("cover_settings_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("logs_json", sa.JSON(), nullable=False),
        sa.Column("frames_json", sa.JSON(), nullable=False),
        sa.Column("selected_frame_ids_json", sa.JSON(), nullable=False),
        sa.Column("cover_preview_json", sa.JSON(), nullable=True),
        sa.Column("plan_id", sa.String(length=64), nullable=True),
        sa.Column("plan_preview_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
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
            ["batch_id"],
            ["local_metadata_batches.id"],
            name=op.f("fk_local_metadata_batch_items_batch_id_local_metadata_batches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_local_metadata_batch_items")),
    )
    op.create_index(
        "ix_local_metadata_batch_items_batch_status",
        "local_metadata_batch_items",
        ["batch_id", "status"],
    )
    op.create_index(
        "ix_local_metadata_batch_items_video_path",
        "local_metadata_batch_items",
        ["video_path"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_local_metadata_batch_items_video_path",
        table_name="local_metadata_batch_items",
    )
    op.drop_index(
        "ix_local_metadata_batch_items_batch_status",
        table_name="local_metadata_batch_items",
    )
    op.drop_table("local_metadata_batch_items")
    op.drop_index(
        "ix_local_metadata_batches_updated_at",
        table_name="local_metadata_batches",
    )
    op.drop_index("ix_local_metadata_batches_status", table_name="local_metadata_batches")
    op.drop_table("local_metadata_batches")
