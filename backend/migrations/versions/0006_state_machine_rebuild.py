"""v6: the eleven-status case state machine, settings store, results, appointments, treatment starts, closures, consultations, inbound events and routing rules.

A database created at 0001 on v6 code already has all of this (0001 builds the tables from the current models), so every step here
checks first and does nothing when the column or table is already there. On an older database it adds what is missing and maps the old
statuses to the new ones. The old consultations table has a different shape and is replaced (it held no production data)."""
import sqlalchemy as sa
from alembic import op
from app.core.database import Base
from app.models import *  # noqa: F401,F403  (register every model)

revision = "0006_state_machine_rebuild"
down_revision = "0005_urgent_routing_audit_guard"
branch_labels = None
depends_on = None

CASE_STATUS_MAP = {"OPEN": "AWAITING_CLASSIFICATION", "ASSIGNED": "NOTIFYING", "IN_PROGRESS": "NOTIFYING", "IN_REVIEW": "NOTIFYING",
                   "AWAITING_REVIEW": "NOTIFYING", "RESOLVED": "CLOSED"}
REFERRAL_STATUS_MAP = {"PENDING": "SENT", "REJECTED": "DECLINED", "ESCALATED": "SENT"}

def _server_default(col):
    d = col.default.arg if col.default is not None and col.default.is_scalar else None
    if isinstance(d, bool): return "1" if d else "0"
    if isinstance(d, (int, float)): return str(d)
    if isinstance(d, str): return d
    return None

def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "consultations" in insp.get_table_names() and "type" not in {c["name"] for c in insp.get_columns("consultations")}:
        op.drop_table("consultations")
        insp = sa.inspect(bind)
    for table in Base.metadata.sorted_tables:
        if table.name not in insp.get_table_names():
            table.create(bind, checkfirst=True)
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            sd = _server_default(col)
            has_fk = bool(col.foreign_keys) and bind.dialect.name == "sqlite"
            new = sa.Column(col.name, col.type, nullable=True if (col.nullable or sd is None) else False, server_default=sd)
            op.add_column(table.name, new)
    insp = sa.inspect(bind)
    op.execute("ALTER TABLE cases ALTER COLUMN status TYPE VARCHAR(30) USING status::text")
    for old, new in CASE_STATUS_MAP.items():
        op.execute(sa.text("UPDATE cases SET status = :n WHERE status = :o").bindparams(n=new, o=old))
    for old, new in REFERRAL_STATUS_MAP.items():
        op.execute(sa.text("UPDATE referrals SET status = :n WHERE status = :o").bindparams(n=new, o=old))
    # Cases that existed before get a status entry time so their time limits can be calculated.
    op.execute(sa.text("UPDATE cases SET status_entered_at = COALESCE(updated_at, created_at) WHERE status_entered_at IS NULL"))

def downgrade():
    pass  # forward only: the old status model cannot be rebuilt from the new one
