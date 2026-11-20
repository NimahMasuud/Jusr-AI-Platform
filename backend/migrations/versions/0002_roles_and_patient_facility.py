
"""Role model update (COORDINATOR, REFERRING_CLINICIAN, RECEIVING_CLINICIAN) and patients.facility_id."""
import sqlalchemy as sa
from alembic import op

revision = "0002_roles_and_patient_facility"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

NEW_ROLES = ("COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN")


def role_exists(bind, role_name):
    """Check whether a PostgreSQL role enum value exists."""
    if bind.dialect.name != "postgresql":
        return True

    result = bind.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'role'
                AND e.enumlabel = :role_name
            )
        """),
        {"role_name": role_name},
    )
    return result.scalar()


def upgrade():
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for role in NEW_ROLES:
                op.execute(
                    f"ALTER TYPE role ADD VALUE IF NOT EXISTS '{role}'"
                )

    # Rename the old coordinator role only if it exists in the database enum.
    if role_exists(bind, "FACILITY_STAFF"):
        op.execute(
            "UPDATE users SET role = 'COORDINATOR' "
            "WHERE role = 'FACILITY_STAFF'"
        )

    columns = [
        c["name"] for c in sa.inspect(bind).get_columns("patients")
    ]

    if "facility_id" not in columns:
        fk = (
            []
            if bind.dialect.name == "sqlite"
            else [sa.ForeignKey("facilities.id")]
        )
        op.add_column(
            "patients",
            sa.Column("facility_id", sa.String(36), *fk, nullable=True),
        )

    op.execute(
        "UPDATE patients SET facility_id = "
        "(SELECT c.facility_id FROM cases c "
        "WHERE c.patient_id = patients.id LIMIT 1) "
        "WHERE facility_id IS NULL"
    )


def downgrade():
    bind = op.get_bind()

    # Reverse the role rename only if the legacy enum value exists.
    if role_exists(bind, "FACILITY_STAFF"):
        op.execute(
            "UPDATE users SET role = 'FACILITY_STAFF' "
            "WHERE role = 'COORDINATOR'"
        )

    if bind.dialect.name == "postgresql":
        op.drop_column("patients", "facility_id")

    # SQLite cannot drop a foreign-key column without a table rebuild;
    # the extra nullable column is harmless.
