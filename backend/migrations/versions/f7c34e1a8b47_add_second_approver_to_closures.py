
"""add second approver to closures

Revision ID: f7c34e1a8b47
Revises: 18032806287e
"""
from alembic import op
import sqlalchemy as sa

revision = "f7c34e1a8b47"
down_revision = "18032806287e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "closures",
        sa.Column("second_approver_id", sa.String(length=36), nullable=True),
    )

    op.create_foreign_key(
        "fk_closures_second_approver_id_users",
        "closures",
        "users",
        ["second_approver_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_closures_second_approver_id_users",
        "closures",
        type_="foreignkey",
    )

    op.drop_column("closures", "second_approver_id")
