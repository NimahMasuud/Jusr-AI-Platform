"""Patient links, responses, tasks, AI suggestions, messages, R-18 delay reasons, patients.birth_year."""
import sqlalchemy as sa
from alembic import op
from app.core.database import Base
from app.models import *  # noqa: F401,F403  (register all tables on Base.metadata)

revision = "0004_links_ai_messages_delay"
down_revision = "0003_referrals"
branch_labels = None
depends_on = None

NEW_TABLES = ["patient_links", "patient_responses", "tasks", "ai_suggestions", "messages"]

def _add(table, column):
    if column.name not in [c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)]:
        op.add_column(table, column)

def upgrade():
    bind = op.get_bind()
    # Creates only the tables that do not exist yet, with their constraints.
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in NEW_TABLES])
    fk = [] if bind.dialect.name == "sqlite" else [sa.ForeignKey("users.id")]  # SQLite cannot add an FK with ADD COLUMN
    _add("patients", sa.Column("birth_year", sa.Integer(), nullable=True))
    _add("cases", sa.Column("delay_reason_code", sa.String(40), nullable=True))
    _add("cases", sa.Column("delay_reason_note", sa.Text(), nullable=True))
    _add("cases", sa.Column("delay_reason_recorded_at", sa.DateTime(timezone=True), nullable=True))
    _add("cases", sa.Column("delay_reason_recorded_by_id", sa.String(36), *fk, nullable=True))

def downgrade():
    # Additive migration; nothing is dropped so that patient responses, messages and audit links are not lost.
    pass
