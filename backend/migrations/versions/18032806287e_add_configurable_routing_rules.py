
"""add configurable routing rules

Revision ID: 18032806287e
Revises: 0006_state_machine_rebuild
"""

from alembic import op
import sqlalchemy as sa

revision = "18032806287e"
down_revision = "0006_state_machine_rebuild"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Create tracker index only if it does not already exist.
    existing_indexes = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("cases")
    }

    tracker_index = op.f("ix_cases_tracker_id")

    if tracker_index not in existing_indexes:
        op.create_index(
            tracker_index,
            "cases",
            ["tracker_id"],
            unique=True,
        )

    # Add foreign keys only if they do not already exist.
    inspector = sa.inspect(bind)

    case_fks = {
        tuple(fk["constrained_columns"])
        for fk in inspector.get_foreign_keys("cases")
    }

    if ("linked_case_id",) not in case_fks:
        op.create_foreign_key(
            "fk_cases_linked_case_id_cases",
            "cases",
            "cases",
            ["linked_case_id"],
            ["id"],
        )

    if ("match_confirmed_by_id",) not in case_fks:
        op.create_foreign_key(
            "fk_cases_match_confirmed_by_id_users",
            "cases",
            "users",
            ["match_confirmed_by_id"],
            ["id"],
        )

    # Add patient record number index only if missing.
    patient_indexes = {
        index["name"]
        for index in inspector.get_indexes("patients")
    }

    patient_index = op.f("ix_patients_record_number")

    if patient_index not in patient_indexes:
        op.create_index(
            patient_index,
            "patients",
            ["record_number"],
            unique=False,
        )

    # Add referral accepted_by foreign key only if missing.
    referral_fks = {
        tuple(fk["constrained_columns"])
        for fk in inspector.get_foreign_keys("referrals")
    }

    if ("accepted_by_id",) not in referral_fks:
        op.create_foreign_key(
            "fk_referrals_accepted_by_id_users",
            "referrals",
            "users",
            ["accepted_by_id"],
            ["id"],
        )


def downgrade():
    # This migration is kept non-destructive for the existing deployment.
    pass
