"""Backend mode: run a helper, then submit the result to the backend as a PENDING suggestion.

The backend stores it and a staff member approves or rejects it there. This service never
changes a case itself (R-02, R-08, R-15).
"""
from typing import Any, Optional
from .audit import AuditLog
from .backend_client import BackendClient, BackendError
from .errors import ApiError
from .mappers import (MappingError, intake_payload, message_payload, referral_payload,
                      summary_payload, urgency_payload)
from .models import Actor, CamelModel, HelperType
from .providers.base import ProviderResult
from .service import HelperService
from .urgency import evaluate
from .verify import camelize


class SubmitResponse(CamelModel):
    status: str  # submitted | no_suggestion | unavailable
    message: str
    backend_suggestion: Optional[dict] = None
    preview: Optional[dict] = None  # what was read or drafted, in case the screen wants to show it
    notices: list[str] = []
    manual_instruction: Optional[str] = None


class SubmitService:
    def __init__(self, helpers: HelperService, client: Optional[BackendClient], facility_ids: dict,
                 model_label: str, rules, audit: AuditLog):
        self.helpers, self.client, self.facility_ids = helpers, client, facility_ids
        self.model_label, self.rules, self.audit = model_label, rules, audit
        self._ids: Optional[dict[str, str]] = None

    def _resolved_facility_ids(self) -> dict[str, str]:
        """config may give IDs directly ({"ids": {...}}) or map mock labels to real facility codes
        ({"codeAliases": {"Facility A": "JUSR-DEMO"}}); the codes are looked up in the backend once."""
        if self._ids is not None:
            return self._ids
        cfg = self.facility_ids or {}
        ids = dict(cfg.get("ids") or (cfg if all(isinstance(v, str) for v in cfg.values()) else {}))
        aliases = cfg.get("codeAliases") or {}
        if aliases and self.client is not None:
            try:
                by_code = {f["code"]: f["id"] for f in self.client.list_facilities()}
            except BackendError as exc:
                self.audit.append("facility_lookup_failed", "ai_service", "ai_service", None,
                                  {"status": exc.status})
                by_code = {}
            for label, code in aliases.items():
                if by_code.get(code):
                    ids[label] = by_code[code]
        self._ids = ids
        return ids

    def submit(self, helper: HelperType, req: Any, actor: Actor, **extra) -> SubmitResponse:
        if self.client is None:
            raise ApiError(503, "BACKEND_NOT_CONFIGURED",
                           "The backend connection is not set up. Set BACKEND_URL and the AI service login.")
        result, used_fallback, early = self.helpers.produce(helper, req, actor)
        if early is not None:
            return SubmitResponse(status=early.status, message=early.message, manual_instruction=early.manual_instruction)
        notices = list(result.notices)
        if used_fallback:
            notices.append("The AI model was not available, so a simple rule-based helper was used.")
        try:
            kind, case_id, payload = self._map(helper, req, result)
        except MappingError as exc:
            raise ApiError(422, "CANNOT_SUBMIT", str(exc)) from exc
        try:
            data = self.client.submit_suggestion(kind, payload, case_id, self.model_label)
        except BackendError as exc:
            self.audit.append("submit_failed", actor.staff_id, actor.role.value, req.case_id,
                              {"kind": kind, "status": exc.status})
            code = "BACKEND_UNAVAILABLE" if exc.status in (0, 502, 503, 504) else "BACKEND_REJECTED"
            raise ApiError(502, code, exc.message, {"backendStatus": exc.status, "backendCode": exc.code}) from exc
        self.audit.append("suggestion_submitted", actor.staff_id, actor.role.value, req.case_id,
                          {"kind": kind, "backend_suggestion_id": data.get("id")})
        return SubmitResponse(status="submitted",
                              message="The suggestion was sent to the backend. A staff member must approve it there.",
                              backend_suggestion=data, preview=camelize(result.content), notices=notices)

    def _map(self, helper: HelperType, req: Any, result: ProviderResult):
        c = result.content
        if helper == HelperType.urgency:
            return "URGENCY", req.case_id, urgency_payload(c)
        if helper == HelperType.message_draft:
            return "MESSAGE_DRAFT", req.case_id, message_payload(c, req.channel)
        if helper == HelperType.summary:
            return "CASE_SUMMARY", req.case_id, summary_payload(c)
        if helper == HelperType.referral_target:
            return "REFERRAL_TARGET", req.case_id, referral_payload(c, self._resolved_facility_ids())
        if helper == HelperType.document_read:
            fields = c["fields"]
            urgency = None
            try:  # the letter's test and result drive the priority, using the clinician-written criteria
                if "test_name" in fields and "result_value" in fields:
                    ev = evaluate(self.rules.criteria,
                                  [{"test": fields["test_name"], "value": float(fields["result_value"])}])
                    urgency = ev["suggestion"]
            except (ValueError, KeyError):
                urgency = None
            # INTAKE proposes a new case, so no caseId goes in the request body
            return "INTAKE", None, intake_payload(req.case_id, req.patient_id, req.facility_id, fields, urgency)
        raise MappingError("This kind of suggestion cannot be submitted.")
