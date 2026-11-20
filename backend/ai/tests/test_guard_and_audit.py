import pytest
from app.audit import AuditLog
from app.guard import ForbiddenForAIService, ai_attempt


@pytest.mark.parametrize("action", ["change_status", "change_owner", "change_urgency", "close_case"])
def test_A02_ai_cannot_change_anything_and_attempt_is_logged(action):
    audit = AuditLog()
    with pytest.raises(ForbiddenForAIService):
        ai_attempt(action, "CASE-1", audit)
    entries = audit.list("CASE-1")
    assert entries[-1]["event_type"] == "ai_forbidden_attempt"
    assert entries[-1]["details"]["action"] == action


def test_ai_may_create_a_suggestion():
    ai_attempt("create_suggestion", "CASE-1", AuditLog())


def test_R01_audit_chain_detects_tampering():
    audit = AuditLog()
    audit.append("a", "S1", "coordinator", "C1", {"x": 1})
    audit.append("b", "S2", "coordinator", "C1", {"y": 2})
    assert audit.verify() is True
    audit._entries[0]["details"]["x"] = 999  # someone edits history
    assert audit.verify() is False
