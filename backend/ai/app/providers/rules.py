"""Simple, predictable helpers that need no AI model.

They are the fallback when the AI provider fails (R-04), and urgency and referral targets are
ALWAYS rule-based: the criteria are written by the clinical lead, not guessed by a model.
"""
import re
from typing import Any
from ..models import (DocumentReadRequest, MessageDraftRequest, ReferralTargetRequest,
                      Source, SummaryRequest, UrgencyRequest)
from ..urgency import Criteria, evaluate, norm_name
from .base import ProviderResult

SIMULATED_NOTICE = "This is a simulated message for a demonstration. No real patient is involved."

LABELS = {
    "patient ref": "patient_ref",
    "facility": "facility",
    "date": "result_date",
    "test": "test_name",
    "result": "result_value",
    "ordering clinician": "ordering_clinician",
    "specialty needed": "specialty_needed",
}
REQUIRED_FIELDS = {"test_name", "result_value", "result_date", "facility"}
LINE = re.compile(r"^\s*([A-Za-z ]+?)\s*:\s*(.+?)\s*$", re.MULTILINE)


class RuleProvider:
    name = "rules"
    label = "rules"

    def __init__(self, urgency_criteria: dict, routing_table: dict, simulated: bool = True):
        self.criteria = Criteria(urgency_criteria)
        self.routing_table = routing_table
        self.simulated = simulated

    # ---- document reader: labelled lines only ----
    def document_read(self, req: DocumentReadRequest) -> ProviderResult:
        fields: dict[str, Any] = {}
        sources: list[Source] = []
        for label, value in LINE.findall(req.document_text):
            key = LABELS.get(label.strip().lower())
            if key and key not in fields:
                fields[key] = value
                sources.append(Source(kind="document", ref=req.document_id,
                                      quote=f"{label.strip()}: {value}"))
        if not fields:
            return ProviderResult("no_suggestion",
                                  "No case details could be read from this document. Please enter them by hand.",
                                  provider=self.name)
        missing = sorted(REQUIRED_FIELDS - set(fields))
        notices = [f"Not found in the document: {', '.join(missing)}."] if missing else []
        return ProviderResult("suggested", "Case details read from the document. Please check each one.",
                              {"fields": fields}, sources,
                              "complete" if not missing else "partial", notices, self.name)

    # ---- message drafter: plain template ----
    def message_draft(self, req: MessageDraftRequest) -> ProviderResult:
        urgent = req.urgency.lower() == "urgent"
        parts = ["Hello,", "", "A screening result from your recent visit needs a follow-up step."]
        sources = [Source(kind="input", ref="next_step"), Source(kind="input", ref="urgency")]
        if req.plain_result_summary:
            parts.append(req.plain_result_summary)
            sources.append(Source(kind="input", ref="plain_result_summary"))
        parts += [f"Next step: {req.next_step}.", ""]
        parts.append("Your care team has marked this as urgent. Please contact us as soon as you can using the details below."
                     if urgent else
                     "Please follow the next step above. If you are worried, contact us using the details below.")
        parts += ["",
                  "Please reply to confirm you received this message. If anything is unclear, tell us and a member of the care team will explain it.",
                  "", f"Contact: {req.contact}"]
        if self.simulated:
            parts += ["", SIMULATED_NOTICE]
        notices = []
        if req.language.lower() != "en":
            notices.append("Only English is available from the simple template. A reviewed translation is needed before sending.")
        return ProviderResult("suggested", "A draft message is ready. A coordinator must approve it before it is sent.",
                              {"language": "en", "text": "\n".join(parts),
                               "requested_language": req.language,
                               "needs_translation_review": req.language.lower() != "en"},
                              sources, "complete", notices, self.name)

    # ---- urgency: clinician-written criteria only ----
    def urgency(self, req: UrgencyRequest) -> ProviderResult:
        if self.criteria.empty:
            return ProviderResult("no_suggestion",
                                  "No urgency criteria have been supplied yet by the clinical lead, so no suggestion can be made.",
                                  provider=self.name)
        ev = evaluate(self.criteria, [r.model_dump(by_alias=True) for r in req.results])
        notices = [f"{n['test']}: {n['why']}" for n in ev["notEvaluated"]] + ev["notes"]
        if ev["suggestion"] is None:
            why = " ".join(f"{n['test']}: {n['why']}" for n in ev["notEvaluated"][:3])
            return ProviderResult("no_suggestion",
                                  "No urgency suggestion can be made. " + why + " A coordinator checks the data and a clinician decides.",
                                  provider=self.name)
        driving = "; ".join(f"{m['ruleId']} ({m['test']} = {m['value']}): {m['reason']}" for m in ev["driving"])
        reason = f"Suggested: {ev['suggestion'].replace('_', ' ')}. {driving}"
        notices.append("These thresholds are DRAFT MOCK values. The lab's own range and flags win. A clinician decides.")
        sources = [Source(kind="config", ref=m["ruleId"]) for m in ev["matched"]] + \
                  [Source(kind="input", ref=f"result:{r.test}") for r in req.results]
        msg = ("Not actionable on this result. Nothing to act on. A clinician confirms."
               if ev["suggestion"] == "no_suggestion" else "An urgency suggestion is ready. A clinician must set the urgency.")
        return ProviderResult("suggested", msg,
                              {"suggested_urgency": ev["suggestion"], "reason": reason, "matched_rules": ev["matched"],
                               "not_evaluated": ev["notEvaluated"], "specialties": ev["specialties"],
                               "look_for": ev["lookFor"], "confidential": ev["confidential"]},
                              sources, "complete" if not ev["notEvaluated"] else "partial", notices, self.name)

    # ---- case summary: one line per event, each pointing at its event ----
    def summary(self, req: SummaryRequest) -> ProviderResult:
        if not req.events:
            return ProviderResult("no_suggestion", "There are no events to summarise yet.", provider=self.name)
        bullets, sources = [], []
        for e in sorted(req.events, key=lambda x: x.timestamp):
            who = f" (staff {e.actor_staff_id})" if e.actor_staff_id else ""
            bullets.append({"text": f"{e.timestamp[:10]} {e.type.replace('_', ' ')}{who}: {e.text}",
                            "sources": [e.event_id]})
            sources.append(Source(kind="event", ref=e.event_id))
        return ProviderResult("suggested", "A case summary is ready. Each line links to its source event.",
                              {"bullets": bullets}, sources, "complete", [], self.name)

    # ---- referral target: routing table only ----
    def referral_target(self, req: ReferralTargetRequest) -> ProviderResult:
        rows = self.routing_table.get("rows", [])
        if not rows:
            return ProviderResult("no_suggestion",
                                  "No routing table has been supplied yet by the clinical lead, so no suggestion can be made.",
                                  provider=self.name)
        wanted = norm_name(req.specialty_needed)
        hits = []
        for i, row in enumerate(rows):
            names = [norm_name(row["specialty"])] + [norm_name(a) for a in row.get("aliases", [])]
            pos = [wanted.find(n) for n in names if n and n in wanted]
            if pos:
                hits.append((min(pos), i))
        if not hits:
            return ProviderResult("no_suggestion",
                                  f"The routing table has no entry for '{req.specialty_needed}'. Please choose by hand.",
                                  provider=self.name)
        options = []
        for _, i in sorted(hits):
            r = rows[i]
            options.append({"specialty": r["specialty"], "service": r["service"], "primary": r["primary"], "backup": r["backup"],
                            "urgent_recipient": r["urgentRecipient"], "urgent_role": r["urgentRole"],
                            "time_to_accept_urgent": r["timeToAcceptUrgent"]})
        return ProviderResult("suggested", "Referral options are ready. The referring clinician chooses.",
                              {"options": options, "reason": "Listed in the routing table (mock facilities). The time to accept is a placeholder."},
                              [Source(kind="config", ref=f"routing_row_{i}") for _, i in sorted(hits)], "complete",
                              ["Facility names are MOCK labels for the demo."], self.name)
