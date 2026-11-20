"""Runs the helpers and handles approvals. The only thing it ever changes is a suggestion."""
import uuid
from typing import Any, Callable, Optional
from .audit import AuditLog, utc_now
from .errors import ApiError
from .guard import ai_attempt
from .models import (Actor, HelperResponse, HelperType, Role, Suggestion, SuggestionStatus)
from .providers.base import HELPER_METHODS, ProviderResult
from .store import SuggestionStore
from .verify import camelize

REQUESTER_ROLES = {Role.coordinator, Role.referring_clinician, Role.receiving_clinician}

MANUAL = {
    HelperType.document_read: "Enter the case details by hand from the document.",
    HelperType.message_draft: "Write the patient message by hand and have it approved as usual.",
    HelperType.urgency: "A clinician sets the urgency by hand.",
    HelperType.summary: "Read the case timeline directly.",
    HelperType.referral_target: "The referring clinician chooses the referral target by hand.",
}


class HelperService:
    def __init__(self, provider, fallback, store: SuggestionStore, audit: AuditLog,
                 approver_roles: dict[str, list[str]], simulated: bool = True,
                 clock: Callable[[], str] = utc_now):
        self.provider = provider
        self.fallback = fallback  # the rule provider (R-04)
        self.store = store
        self.audit = audit
        self.approver_roles = approver_roles
        self.simulated = simulated
        self.clock = clock

    # ---- run a helper (shared by the standalone and the submit-to-backend flows) ----
    def produce(self, helper: HelperType, req: Any, actor: Actor):
        """Returns (result, used_fallback, early_response). R-04: a failing helper never breaks the flow."""
        if actor.role not in REQUESTER_ROLES:
            raise ApiError(403, "ROLE_CANNOT_REQUEST", "Your role cannot ask for AI suggestions.")
        ai_attempt("create_suggestion", req.case_id, self.audit)  # the one thing the AI may do

        result: Optional[ProviderResult] = None
        used_fallback = False
        try:
            result = getattr(self.provider, HELPER_METHODS[helper])(req)
        except Exception as exc:
            self.audit.append("ai_helper_failed", actor.staff_id, actor.role.value, req.case_id,
                              {"helper": helper.value, "provider": getattr(self.provider, "name", "?"),
                               "error": type(exc).__name__})
            if self.fallback is not None and self.fallback is not self.provider:
                try:
                    result = getattr(self.fallback, HELPER_METHODS[helper])(req)
                    used_fallback = True
                except Exception as exc2:
                    self.audit.append("ai_fallback_failed", actor.staff_id, actor.role.value, req.case_id,
                                      {"helper": helper.value, "error": type(exc2).__name__})
            if result is None or result.status != "suggested":
                msg = ("The AI helper is not available right now. You can carry on by hand."
                       if result is None else result.message)
                return None, used_fallback, HelperResponse(status="unavailable", message=msg,
                                                           manual_instruction=MANUAL[helper])
        if result.status != "suggested":
            self.audit.append("ai_no_suggestion", actor.staff_id, actor.role.value, req.case_id,
                              {"helper": helper.value, "reason": result.message})
            return None, used_fallback, HelperResponse(status="no_suggestion", message=result.message,
                                                       manual_instruction=MANUAL[helper])
        return result, used_fallback, None

    # ---- ask a helper for a suggestion (standalone mode: this service keeps the suggestion) ----
    def request(self, helper: HelperType, req: Any, actor: Actor) -> HelperResponse:
        result, used_fallback, early = self.produce(helper, req, actor)
        if early is not None:
            return early
        notices = list(result.notices)
        provider_name = result.provider
        if used_fallback:
            provider_name = f"{result.provider} (fallback)"
            notices.append("The AI model was not available, so a simple rule-based helper was used.")
        suggestion = Suggestion(
            id="sug_" + uuid.uuid4().hex[:12], case_id=req.case_id, helper=helper,
            content=camelize(result.content), sources=result.sources, completeness=result.completeness,
            provider=provider_name, notices=notices, requested_by=actor.staff_id,
            created_at=self.clock(), simulated=self.simulated,
        )
        self.store.add(suggestion)
        self.audit.append("suggestion_created", actor.staff_id, actor.role.value, req.case_id,
                          {"suggestion_id": suggestion.id, "helper": helper.value,
                           "provider": provider_name, "sources": len(suggestion.sources)})
        return HelperResponse(status="suggested", message=result.message, suggestion=suggestion)

    # ---- a person approves, edits or rejects ----
    def decide(self, suggestion_id: str, decision: str, edited_content: Optional[dict],
               note: Optional[str], actor: Actor) -> Suggestion:
        s = self.store.get(suggestion_id)
        if s is None:
            raise ApiError(404, "SUGGESTION_NOT_FOUND", "That suggestion could not be found.")
        allowed = self.approver_roles.get(s.helper.value, [])
        if actor.role.value not in allowed:
            self.audit.append("decision_refused", actor.staff_id, actor.role.value, s.case_id,
                              {"suggestion_id": s.id, "reason": "role_not_allowed"})
            raise ApiError(403, "ROLE_CANNOT_DECIDE",
                           "Your role cannot approve this kind of suggestion.",
                           {"allowedRoles": allowed})
        if s.status != SuggestionStatus.pending:
            raise ApiError(409, "ALREADY_DECIDED", "This suggestion has already been decided.")
        if decision not in {"approve", "edit", "reject"}:
            raise ApiError(422, "UNKNOWN_DECISION", "The decision must be approve, edit or reject.")
        if decision == "edit" and not edited_content:
            raise ApiError(422, "EDIT_NEEDS_CONTENT", "Please give the corrected content when you edit.")

        s.status = {"approve": SuggestionStatus.accepted, "edit": SuggestionStatus.edited,
                    "reject": SuggestionStatus.rejected}[decision]
        s.edited_content = edited_content if decision == "edit" else None
        s.decided_by, s.decided_role = actor.staff_id, actor.role.value
        s.decided_at, s.decision_note = self.clock(), note
        self.store.update(s)
        self.audit.append(f"suggestion_{s.status.value}", actor.staff_id, actor.role.value, s.case_id,
                          {"suggestion_id": s.id, "helper": s.helper.value, "note": note})
        return s
