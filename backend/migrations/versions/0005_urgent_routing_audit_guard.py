"""Urgent specialty routing columns, users.specialty, and append-only audit_events triggers (R-21)."""
import sqlalchemy as sa
from alembic import op
from app.core import audit_guard

revision = "0005_urgent_routing_audit_guard"
down_revision = "0004_links_ai_messages_delay"
branch_labels = None
depends_on = None

def _add(table, column):
    if column.name not in [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]:
        op.add_column(table, column)

def upgrade():
    bind = op.get_bind()
    fk = [] if bind.dialect.name == "sqlite" else [sa.ForeignKey("users.id")]  # SQLite cannot add an FK with ADD COLUMN
    _add("users", sa.Column("specialty", sa.String(60), nullable=True))
    _add("cases", sa.Column("required_specialty", sa.String(60), nullable=True))
    _add("cases", sa.Column("routing_status", sa.String(30), nullable=True))
    _add("cases", sa.Column("routed_clinician_id", sa.String(36), *fk, nullable=True))
    _add("cases", sa.Column("routing_stage", sa.Integer(), nullable=False, server_default="0"))
    _add("cases", sa.Column("routing_first_limit_minutes", sa.Integer(), nullable=True))
    _add("cases", sa.Column("routing_second_limit_minutes", sa.Integer(), nullable=True))
    _add("cases", sa.Column("routing_started_at", sa.DateTime(timezone=True), nullable=True))
    _add("cases", sa.Column("routing_due_at", sa.DateTime(timezone=True), nullable=True))
    _add("cases", sa.Column("routing_accepted_at", sa.DateTime(timezone=True), nullable=True))
    _add("cases", sa.Column("routing_exception_reason", sa.Text(), nullable=True))
    _add("cases", sa.Column("routing_tried", sa.JSON(), nullable=True))
    existing = {i["name"] for i in sa.inspect(bind).get_indexes("cases")}
    for name, col in (("ix_cases_routing_status", "routing_status"), ("ix_cases_routed_clinician_id", "routed_clinician_id")):
        if name not in existing:
            op.create_index(name, "cases", [col])
    audit_guard.install(bind)

def downgrade():
    # Remove the append-only guard only; routing columns are kept so routed cases are not lost.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    elif bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
