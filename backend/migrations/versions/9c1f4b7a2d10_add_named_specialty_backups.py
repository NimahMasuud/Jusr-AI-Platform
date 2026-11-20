"""add named specialty backups

Revision ID: 9c1f4b7a2d10
Revises: f7c34e1a8b47
"""
from alembic import op
import sqlalchemy as sa

revision = "9c1f4b7a2d10"
down_revision = "f7c34e1a8b47"
branch_labels = None
depends_on = None


def upgrade():
    # The demo bootstrap (create_all) may already have created this table.
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "specialty_backups" not in tables:
        op.create_table(
            "specialty_backups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("specialty", sa.String(length=60), nullable=False),
            sa.Column("clinician_id", sa.String(length=36), nullable=False),
            sa.Column("facility_id", sa.String(length=36), nullable=True),
            sa.Column("changed_by_id", sa.String(length=36), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["clinician_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
            sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"]),
            sa.UniqueConstraint("specialty"),
        )
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("specialty_backups")}
    if "ix_specialty_backups_specialty" not in indexes:
        op.create_index("ix_specialty_backups_specialty", "specialty_backups", ["specialty"])


def downgrade():
    op.drop_index("ix_specialty_backups_specialty", table_name="specialty_backups")
    op.drop_table("specialty_backups")
