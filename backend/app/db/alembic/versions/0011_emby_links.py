"""Create Emby link table.

Revision ID: 0011_emby_links
Revises: 0010_watch_monitor_state
Create Date: 2026-07-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_emby_links"
down_revision: Union[str, None] = "0010_watch_monitor_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emby_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("metadata_record_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("emby_path", sa.Text(), nullable=True),
        sa.Column("emby_item_id", sa.String(length=255), nullable=True),
        sa.Column("emby_person_id", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
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
            ["actor_id"],
            ["actors.id"],
            name=op.f("fk_emby_links_actor_id_actors"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_emby_links_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["metadata_record_id"],
            ["metadata_records.id"],
            name=op.f("fk_emby_links_metadata_record_id_metadata_records"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_emby_links")),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "emby_item_id",
            name="uq_emby_links_entity_item",
        ),
    )
    op.create_index("ix_emby_links_job_id", "emby_links", ["job_id"])
    op.create_index("ix_emby_links_actor_id", "emby_links", ["actor_id"])
    op.create_index(
        "ix_emby_links_metadata_record_id",
        "emby_links",
        ["metadata_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_emby_links_metadata_record_id", table_name="emby_links")
    op.drop_index("ix_emby_links_actor_id", table_name="emby_links")
    op.drop_index("ix_emby_links_job_id", table_name="emby_links")
    op.drop_table("emby_links")
