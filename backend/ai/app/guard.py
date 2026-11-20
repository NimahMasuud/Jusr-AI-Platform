"""R-08 and R-15: the AI service account can write suggestions only.

It cannot change a status, owner, urgency or closure, and it cannot close a case.
Any attempt is refused and logged (acceptance test A-02).

NOTE FOR EMMANUEL: the real back end must enforce this too. This module is our side of the rule.
"""
from .audit import AuditLog

ALLOWED_AI_ACTIONS = {"create_suggestion"}
FORBIDDEN_AI_ACTIONS = {"change_status", "change_owner", "change_urgency", "close_case"}


class ForbiddenForAIService(Exception):
    def __init__(self, action: str):
        self.action = action
        super().__init__(
            "The AI helper can only make suggestions. A person must change a status, "
            "owner, urgency or closure."
        )


def ai_attempt(action: str, case_id: str, audit: AuditLog) -> None:
    if action in ALLOWED_AI_ACTIONS:
        return
    audit.append("ai_forbidden_attempt", "ai_service", "ai_service", case_id, {"action": action})
    raise ForbiddenForAIService(action)
