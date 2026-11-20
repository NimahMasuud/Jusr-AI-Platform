"""Referral workflow columns, consultation.referral_id and audit_events.actor_role (R-01)."""
import sqlalchemy as sa
from alembic import op

revision = "0003_referrals"
down_revision = "0002_roles_and_patient_facility"
branch_labels = None
depends_on = None

def _add(table, column):
    existing = [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]
    if column.name not in existing:
        op.add_column(table, column)

def _fkargs(fk):
    return [fk] if fk is not None else []

def upgrade():
    # SQLite cannot add a foreign-key constraint with ADD COLUMN; it is enforced on PostgreSQL only.
    fk = (lambda target: None) if op.get_bind().dialect.name == "sqlite" else (lambda target: sa.ForeignKey(target))
    _add("referrals", sa.Column("receiving_clinician_id", sa.String(36), *_fkargs(fk("users.id")), nullable=True))
    _add("referrals", sa.Column("referred_by_id", sa.String(36), *_fkargs(fk("users.id")), nullable=True))
    _add("referrals", sa.Column("reason", sa.Text(), nullable=True))
    _add("referrals", sa.Column("rejection_reason", sa.Text(), nullable=True))
    _add("referrals", sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add("referrals", sa.Column("escalation_reason", sa.Text(), nullable=True))
    _add("referrals", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    _add("referrals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    _add("referrals", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE referrals SET updated_at = created_at WHERE updated_at IS NULL")
    _add("consultations", sa.Column("referral_id", sa.String(36), *_fkargs(fk("referrals.id")), nullable=True))
    _add("audit_events", sa.Column("actor_role", sa.String(40), nullable=True))
    op.execute("UPDATE audit_events SET actor_role = (SELECT u.role FROM users u WHERE u.id = audit_events.actor_id) WHERE actor_role IS NULL AND actor_id IS NOT NULL")

def downgrade():
    # Additive migration; columns are left in place to avoid destroying referral and audit data.
    pass
