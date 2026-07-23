"""Create HTTP cache table.

Revision ID: 0004_http_cache
Revises: 0003_media_items
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_http_cache"
down_revision: Union[str, None] = "0003_media_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "http_cache",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("cache_key", name=op.f("pk_http_cache")),
    )


def downgrade() -> None:
    op.drop_table("http_cache")
