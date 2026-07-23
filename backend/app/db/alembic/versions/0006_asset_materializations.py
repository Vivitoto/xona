"""Create asset materialization cache table.

Revision ID: 0006_asset_materializations
Revises: 0005_metadata_records
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_asset_materializations"
down_revision: Union[str, None] = "0005_metadata_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_materializations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("cache_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("observed_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'materialized'"),
            nullable=False,
        ),
        sa.Column("missing_reason", sa.Text(), nullable=True),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column("actor_source_id", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_materializations")),
    )
    op.create_index(
        "ix_asset_materializations_source_path",
        "asset_materializations",
        ["source_url", "relative_path", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_materializations_source_path",
        table_name="asset_materializations",
    )
    op.drop_table("asset_materializations")
