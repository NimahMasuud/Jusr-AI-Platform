"""Patient phone for SMS link delivery, plus simulated SMS delivery metadata on patient links."""
import sqlalchemy as sa
from alembic import op

revision = "0007_patient_phone_and_link_sms"
down_revision = "9c1f4b7a2d10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("patients", sa.Column("phone", sa.String(length=40), nullable=True))
    op.add_column(
        "patient_links",
        sa.Column("delivery_channel", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "patient_links",
        sa.Column("delivery_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "patient_links",
        sa.Column("delivered_to", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "patient_links",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("patient_links", "delivered_at")
    op.drop_column("patient_links", "delivered_to")
    op.drop_column("patient_links", "delivery_status")
    op.drop_column("patient_links", "delivery_channel")
    op.drop_column("patients", "phone")
