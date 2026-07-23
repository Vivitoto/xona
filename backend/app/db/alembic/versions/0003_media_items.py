"""Create media item tables.

Revision ID: 0003_media_items
Revises: 0002_auth_tables
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_media_items"
down_revision: Union[str, None] = "0002_auth_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("storage_root_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("group_key", sa.Text(), nullable=False),
        sa.Column("multipart_index", sa.Integer(), nullable=True),
        sa.Column("identity", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
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
            ["storage_root_id"],
            ["storage_roots.id"],
            name=op.f("fk_media_items_storage_root_id_storage_roots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_items")),
        sa.UniqueConstraint("identity", name=op.f("uq_media_items_identity")),
        sa.UniqueConstraint("path", name=op.f("uq_media_items_path")),
    )
    op.create_table(
        "media_sidecars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_media_sidecars_media_item_id_media_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_sidecars")),
    )


def downgrade() -> None:
    op.drop_table("media_sidecars")
    op.drop_table("media_items")
