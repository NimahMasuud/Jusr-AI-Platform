"""Turns helper output into the backend's suggestion payloads (backend /api/v1/ai/suggestions).

Nothing is guessed. If something the backend needs is missing (a patient ID, a facility ID),
MappingError says what, in plain language, and nothing is sent.
"""
from typing import Any, Optional

PRIORITY = {"urgent": "URGENT", "clinician_decides": "HIGH", "routine": "NORMAL", "no_suggestion": "NORMAL"}
ACTIONABILITY = {"urgent": "ACTIONABLE", "routine": "ACTIONABLE",
                 "clinician_decides": "NEEDS_REVIEW", "no_suggestion": "NOT_ACTIONABLE"}


class MappingError(Exception):
    pass


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def urgency_payload(content: dict[str, Any]) -> dict[str, Any]:
    s = content["suggested_urgency"]
    rationale = content["reason"]
    if content.get("look_for"):
        rationale += " Clinician to check: " + "; ".join(content["look_for"]) + "."
    if content.get("specialties"):
        rationale += " Suggested specialty: " + "; ".join(content["specialties"]) + "."
    return {"priority": PRIORITY[s], "actionability": ACTIONABILITY[s], "rationale": _cut(rationale, 2000)}


def message_payload(content: dict[str, Any], channel: str, purpose: str = "Patient notification") -> dict[str, Any]:
    if channel.upper() not in ("SMS", "EMAIL"):
        raise MappingError("The channel must be SMS or EMAIL.")
    if content.get("needs_translation_review"):
        raise MappingError("This draft needs a reviewed translation before it can be submitted. Use English, or review the translation first.")
    return {"channel": channel.upper(), "body": _cut(content["text"], 2000), "purpose": purpose}


def summary_payload(content: dict[str, Any]) -> dict[str, Any]:
    bullets = content["bullets"]
    citations, seen = [], set()
    for b in bullets:
        for eid in b["sources"]:
            if eid not in seen:
                seen.add(eid)
                citations.append({"sourceType": "AUDIT_EVENT", "sourceId": eid, "excerpt": _cut(b["text"], 500)})
    if not citations:
        raise MappingError("The summary has no source events to cite, so it cannot be submitted.")
    return {"summary": _cut("\n".join(b["text"] for b in bullets), 5000), "citations": citations[:50]}


def referral_payload(content: dict[str, Any], facility_ids: dict[str, str]) -> dict[str, Any]:
    options = content["options"]
    ordered: list[tuple[str, str]] = []  # (facility code, why)
    for i, o in enumerate(options):
        ordered.append((o["primary"]["facilityCode"], f"{o['specialty']}: {o['primary']['text']}"))
        if o.get("backup") and o["backup"].get("facilityCode"):
            ordered.append((o["backup"]["facilityCode"], f"{o['specialty']} (backup): {o['backup']['text']}"))
    missing = sorted({code for code, _ in ordered if code not in facility_ids})
    if missing:
        raise MappingError("These facilities have no backend ID in config/facility_ids.json: " + ", ".join(missing) +
                           ". The backend team must supply them.")
    main_code, main_why = ordered[0]
    alts, used = [], {main_code}
    for code, why in ordered[1:]:
        if code in used or len(alts) >= 5:
            continue
        used.add(code)
        alts.append({"receivingFacilityId": facility_ids[code], "rationale": _cut(why, 2000)})
    return {"receivingFacilityId": facility_ids[main_code],
            "rationale": _cut(f"Routing table (mock). {main_why}", 2000), "alternatives": alts}


def intake_payload(case_number: str, patient_id: Optional[str], facility_id: Optional[str],
                   fields: dict[str, Any], urgency: Optional[str]) -> dict[str, Any]:
    if not patient_id:
        raise MappingError("An intake suggestion needs the backend patient ID.")
    if not facility_id:
        raise MappingError("An intake suggestion needs the backend facility ID.")
    shown = ", ".join(f"{k}: {v}" for k, v in fields.items())
    rationale = f"Read from the document. {shown}."
    if urgency:
        rationale += f" Urgency suggestion from the criteria: {urgency.replace('_', ' ')}."
    return {"patientId": patient_id, "caseId": _cut(case_number, 40), "facilityId": facility_id,
            "priority": PRIORITY.get(urgency or "routine", "NORMAL"),
            "nextActionCode": "PATIENT_NOTIFICATION", "nextActionLabel": "Patient notification",
            "rationale": _cut(rationale, 2000)}
