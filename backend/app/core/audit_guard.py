"""R-21: audit events are append-only. Database triggers reject UPDATE and DELETE on audit_events, so the
guarantee holds even for code that bypasses the ORM. For defence in depth, also revoke UPDATE/DELETE/TRUNCATE
on the table from the application's database role (see README)."""

MESSAGE = "audit_events is append-only (R-21)"

POSTGRESQL = [
    f"CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION '{MESSAGE}'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events",
    "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()",
]

SQLITE = [
    f"CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END",
    f"CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END",
]

def install(connection) -> None:
    """Idempotently install the triggers on an open connection."""
    statements = {"postgresql": POSTGRESQL, "sqlite": SQLITE}.get(connection.dialect.name, [])
    for statement in statements:
        connection.exec_driver_sql(statement)

class AuditImmutableError(Exception):
    pass
