"""Create actor cache tables.

Revision ID: 0007_actors
Revises: 0006_asset_materializations
Create Date: 2026-07-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_actors"
down_revision: Union[str, None] = "0006_asset_materializations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'xchina'"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("portrait_source_url", sa.Text(), nullable=True),
        sa.Column("portrait_cache_path", sa.Text(), nullable=True),
        sa.Column("portrait_sha256", sa.String(length=64), nullable=True),
        sa.Column("portrait_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("biography", sa.Text(), nullable=True),
        sa.Column("profile_fields", sa.JSON(), nullable=False),
        sa.Column("associated_works", sa.JSON(), nullable=False),
        sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("emby_person_id", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actors")),
        sa.UniqueConstraint("source", "source_id", name="uq_actors_source_id"),
    )
    op.create_table(
        "actor_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["actors.id"],
            name=op.f("fk_actor_aliases_actor_id_actors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actor_aliases")),
        sa.UniqueConstraint("actor_id", "alias", name="uq_actor_aliases_actor_alias"),
    )
    op.create_table(
        "actor_media_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("metadata_record_id", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["actors.id"],
            name=op.f("fk_actor_media_links_actor_id_actors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["metadata_record_id"],
            ["metadata_records.id"],
            name=op.f("fk_actor_media_links_metadata_record_id_metadata_records"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_actor_media_links")),
        sa.UniqueConstraint(
            "actor_id",
            "source_id",
            name="uq_actor_media_links_actor_source",
        ),
    )


def downgrade() -> None:
    op.drop_table("actor_media_links")
    op.drop_table("actor_aliases")
    op.drop_table("actors")
