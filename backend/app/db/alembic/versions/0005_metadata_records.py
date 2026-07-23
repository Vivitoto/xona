"""Create metadata and search tables.

Revision ID: 0005_metadata_records
Revises: 0004_http_cache
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_metadata_records"
down_revision: Union[str, None] = "0004_http_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_title", sa.Text(), nullable=True),
        sa.Column("normalized_json", sa.JSON(), nullable=False),
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
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_metadata_records_media_item_id_media_items"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metadata_records")),
        sa.UniqueConstraint(
            "media_item_id",
            "source",
            "source_id",
            name="uq_metadata_records_media_source",
        ),
    )
    op.create_table(
        "search_queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("normalized_input", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["media_item_id"],
            ["media_items.id"],
            name=op.f("fk_search_queries_media_item_id_media_items"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_queries")),
    )
    op.create_table(
        "search_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_query_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_candidate_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("candidate_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["search_query_id"],
            ["search_queries.id"],
            name=op.f("fk_search_candidates_search_query_id_search_queries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_candidates")),
        sa.UniqueConstraint(
            "search_query_id",
            "source",
            "source_candidate_id",
            name="uq_search_candidates_query_source",
        ),
    )


def downgrade() -> None:
    op.drop_table("search_candidates")
    op.drop_table("search_queries")
    op.drop_table("metadata_records")
