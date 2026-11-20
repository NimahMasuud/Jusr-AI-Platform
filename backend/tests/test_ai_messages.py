from datetime import datetime, timedelta, timezone
import pytest
from app.main import app
from app.models.entities import Message
from app.services.messaging import get_message_provider

def err(r, status, code=None):
    assert r.status_code == status, r.text
    assert r.json()["success"] is False
    if code: assert r.json()["error"]["code"] == code

def submit(client, org, kind, payload, case="CA", who="ai", **extra):
    body = {"kind": kind, "payload": payload, **extra}
    if case: body["caseId"] = case
    return client.post("/api/ai/suggestions", headers=org["auth"](who), json=body)

def sub_ok(client, org, *a, **kw):
    r = submit(client, org, *a, **kw); assert r.status_code == 200, r.text
    return r.json()["data"]

def decide(client, org, sid, op="approve", who="coord", body=None):
    return client.post(f"/api/ai/suggestions/{sid}/{op}", headers=org["auth"](who), json=body or {})

def case_of(client, org, number="CA"):
    return next(c for c in client.get("/api/worklist", headers=org["auth"]("national")).json()["data"]["cases"] if c["caseId"] == number)

def events(client, org, case="ca"):
    return client.get(f"/api/cases/{org['ids'][case]}/events", headers=org["auth"]("national")).json()["data"]

def delay(client, org):
    client.post(f"/api/cases/{org['ids']['ca']}/delay-reason", headers=org["auth"]("coord"), json={"code": "RESULT_OR_DATA_MISSING"})

# ---------- the AI service is strictly read-only ----------

def test_ai_service_can_only_submit_suggestions(client, org):
    ids, h = org["ids"], org["auth"]("ai")
    calls = [("post", f"/api/cases/{ids['ca']}/transition", {"status": "IN_PROGRESS"}), ("post", f"/api/cases/{ids['ca']}/assign", {"coordinatorId": ids["coord"]}),
             ("post", f"/api/cases/{ids['ca']}/delay-reason", {"code": "OTHER", "note": "x"}), ("post", f"/api/cases/{ids['ca']}/links", None),
             ("post", f"/api/cases/{ids['ca']}/assisted-responses", {"acknowledged": True, "understood": True, "confidence": 3, "explanationStatus": "EXPLAINED", "callbackRequested": False}), ("post", "/api/patients", {"displayLabel": "x"}),
             ("post", "/api/referrals", {"caseId": ids["ca"], "receivingFacilityId": ids["fb"]}),
             ("post", "/api/messages", {"caseId": ids["ca"], "channel": "SMS", "body": "x"}), ("post", "/api/messages/process-due", None)]
    for method, path, body in calls:
        r = getattr(client, method)(path, headers=h, json=body) if body is not None else getattr(client, method)(path, headers=h)
        assert r.status_code == 403, (path, r.status_code)
    s = sub_ok(client, org, "URGENCY", {"priority": "NORMAL", "actionability": "ACTIONABLE", "rationale": "r"})
    for op in ("approve", "reject"): err(decide(client, org, s["id"], op, "ai", {"reason": "x"}), 403)

def test_only_the_ai_service_submits(client, org):
    for who in ("coord", "refer", "national", "fadmin", "patient"):
        r = submit(client, org, "URGENCY", {"priority": "NORMAL", "actionability": "ACTIONABLE", "rationale": "r"}, who=who)
        assert r.status_code == 403, who

def test_ai_service_reads_the_facility_map_for_referral_suggestions(client, org):
    r = client.get("/api/ai/suggestions/facilities", headers=org["auth"]("ai"))
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert {row["code"] for row in rows} == {"JUSR-DEMO", "DEMO-RRH", "DEMO-DC"}
    assert all(row["id"] and row["name"] for row in rows)
    assert client.get("/api/ai/suggestions/facilities", headers=org["auth"]("coord")).status_code == 403

def test_submission_validation(client, org):
    good = {"priority": "NORMAL", "actionability": "ACTIONABLE", "rationale": "r"}
    err(submit(client, org, "URGENCY", {"priority": "NORMAL"}), 422, "INVALID_SUGGESTION_PAYLOAD")
    err(submit(client, org, "URGENCY", {**good, "priority": "BOGUS"}), 422, "INVALID_SUGGESTION_PAYLOAD")
    err(submit(client, org, "BOGUS", good), 422, "VALIDATION_ERROR")
    err(submit(client, org, "URGENCY", good, case=None), 422, "CASE_REQUIRED")
    err(submit(client, org, "URGENCY", good, case="NOPE"), 404)
    err(submit(client, org, "URGENCY", good, confidence=1.5), 422, "VALIDATION_ERROR")
    err(submit(client, org, "MESSAGE_DRAFT", {"channel": "FAX", "body": "x"}), 422, "INVALID_SUGGESTION_PAYLOAD")

# ---------- suggestions change nothing until staff approve ----------

def test_urgency_suggestion_needs_approval(client, org):
    s = sub_ok(client, org, "URGENCY", {"priority": "NORMAL", "actionability": "NEEDS_REVIEW", "rationale": "Low risk"}, model="triage-1", confidence=0.8)
    assert s["status"] == "PENDING" and s["requiresStaffApproval"] is True
    assert case_of(client, org)["priority"] == "URGENT"                       # unchanged
    err(decide(client, org, s["id"], "approve", "fadmin"), 403)
    err(decide(client, org, s["id"], "approve", "recv"), 403)
    err(decide(client, org, s["id"], "approve", "coordB"), 404)
    err(decide(client, org, s["id"], "approve", "coord"), 403)
    d = decide(client, org, s["id"], "approve", "refer").json()["data"]
    assert d["status"] == "APPROVED" and d["decidedById"] == org["ids"]["refer"] and d["applied"]["priority"] == "NORMAL"
    assert case_of(client, org)["priority"] == "NORMAL"
    ev = [e for e in events(client, org) if e["eventType"] in ("AI_SUGGESTION_SUBMITTED", "CASE_PRIORITY_CHANGED", "AI_SUGGESTION_APPROVED")]
    assert [(e["eventType"], e["actorRole"]) for e in ev] == [("AI_SUGGESTION_SUBMITTED", "AI_SERVICE"), ("CASE_PRIORITY_CHANGED", "REFERRING_CLINICIAN"), ("AI_SUGGESTION_APPROVED", "REFERRING_CLINICIAN")]
    err(decide(client, org, s["id"], "approve", "refer"), 409, "SUGGESTION_ALREADY_DECIDED")
    err(decide(client, org, s["id"], "reject", "refer", body={"reason": "late"}), 409, "SUGGESTION_ALREADY_DECIDED")

def test_rejecting_needs_a_reason_and_changes_nothing(client, org):
    s = sub_ok(client, org, "URGENCY", {"priority": "NORMAL", "actionability": "ACTIONABLE", "rationale": "r"})
    err(decide(client, org, s["id"], "reject"), 422, "VALIDATION_ERROR")
    err(decide(client, org, s["id"], "reject", body={"reason": "  "}), 422, "VALIDATION_ERROR")
    d = decide(client, org, s["id"], "reject", body={"reason": "Clinically wrong"}).json()["data"]
    assert d["status"] == "REJECTED" and d["decisionNote"] == "Clinically wrong"
    assert case_of(client, org)["priority"] == "URGENT"

def test_suggestion_list_filters_and_scope(client, org):
    a = sub_ok(client, org, "URGENCY", {"priority": "NORMAL", "actionability": "ACTIONABLE", "rationale": "r"})
    sub_ok(client, org, "MESSAGE_DRAFT", {"channel": "SMS", "body": "Hello"})
    lst = lambda who, q="": client.get(f"/api/ai/suggestions{q}", headers=org["auth"](who)).json()
    assert lst("coord")["meta"]["total"] == 2 and lst("coordB")["meta"]["total"] == 0
    assert lst("coord", "?kind=URGENCY")["meta"]["total"] == 1 and lst("coord", "?caseId=CA")["meta"]["total"] == 2
    decide(client, org, a["id"], "approve", "refer")
    assert lst("coord", "?status=PENDING")["meta"]["total"] == 1 and lst("ai")["meta"]["total"] == 2
    err(client.get("/api/ai/suggestions", headers=org["auth"]("fadmin")), 403)
    err(client.get("/api/ai/suggestions?kind=NOPE", headers=org["auth"]("coord")), 422, "VALIDATION_ERROR")
    err(client.get(f"/api/ai/suggestions/{a['id']}", headers=org["auth"]("coordB")), 404)

def test_edit_only_allowed_on_message_drafts(client, org):
    s = sub_ok(client, org, "URGENCY", {"priority": "NORMAL", "actionability": "ACTIONABLE", "rationale": "r"})
    err(decide(client, org, s["id"], "approve", "refer", body={"editedBody": "x"}), 422, "EDIT_NOT_ALLOWED")

# ---------- case summaries with source citations ----------

def test_case_summary_requires_real_citations(client, org):
    ids = org["ids"]; delay(client, org)
    ev_id = events(client, org)[0]["id"]
    other_ev = events(client, org, "cb")
    summary = "Overdue case awaiting results."
    err(submit(client, org, "CASE_SUMMARY", {"summary": summary, "citations": []}), 422, "INVALID_SUGGESTION_PAYLOAD")
    err(submit(client, org, "CASE_SUMMARY", {"summary": summary}), 422, "INVALID_SUGGESTION_PAYLOAD")
    err(submit(client, org, "CASE_SUMMARY", {"summary": summary, "citations": [{"sourceType": "AUDIT_EVENT", "sourceId": "made-up"}]}), 422, "INVALID_CITATION")
    err(submit(client, org, "CASE_SUMMARY", {"summary": summary, "citations": [{"sourceType": "CASE", "sourceId": ids["cb"]}]}), 422, "INVALID_CITATION")  # another case
    err(submit(client, org, "CASE_SUMMARY", {"summary": summary, "citations": [{"sourceType": "SCREENING", "sourceId": "x"}]}), 422, "INVALID_CITATION")
    err(client.get("/api/ai/suggestions/cases/CA/summary", headers=org["auth"]("coord")), 404)
    s = sub_ok(client, org, "CASE_SUMMARY", {"summary": summary, "citations": [{"sourceType": "AUDIT_EVENT", "sourceId": ev_id, "excerpt": "delay reason recorded"}, {"sourceType": "CASE", "sourceId": ids["ca"]}]})
    err(client.get("/api/ai/suggestions/cases/CA/summary", headers=org["auth"]("coord")), 404)   # not approved yet
    decide(client, org, s["id"])
    got = client.get("/api/ai/suggestions/cases/CA/summary", headers=org["auth"]("coord")).json()["data"]
    assert got["payload"]["summary"] == summary and len(got["payload"]["citations"]) == 2 and got["status"] == "APPROVED"
    err(client.get("/api/ai/suggestions/cases/CA/summary", headers=org["auth"]("coordB")), 404)

# ---------- referral-target suggestions ----------

def test_referral_target_creates_the_referral_only_on_approval(client, org):
    ids = org["ids"]
    s = sub_ok(client, org, "REFERRAL_TARGET", {"receivingFacilityId": ids["fb"], "rationale": "Nearest colposcopy", "alternatives": [{"receivingFacilityId": ids["fc"], "rationale": "Farther"}]})
    assert client.get("/api/referrals", headers=org["auth"]("national")).json()["meta"]["total"] == 1       # only the seeded one
    err(decide(client, org, s["id"], "approve", "refer"), 422, "ACKNOWLEDGEMENT_REQUIRED")
    assert client.get(f"/api/ai/suggestions/{s['id']}", headers=org["auth"]("coord")).json()["data"]["status"] == "PENDING"

    ack = client.post(
        f"/api/cases/{ids['ca']}/assisted-responses",
        headers=org["auth"]("coord"),
        json={"acknowledged": True, "understood": "YES", "confidence": 4,
              "explanationStatus": "EXPLAINED", "callbackRequested": False},
    )
    assert ack.status_code == 200, ack.text

    d = decide(client, org, s["id"], "approve", "refer").json()["data"]
    assert d["status"] == "APPROVED"
    ref = client.get(f"/api/referrals/{d['applied']['referralId']}", headers=org["auth"]("refer")).json()["data"]
    assert ref["status"] == "SENT" and ref["receivingFacility"]["name"] == "B" and ref["reason"] == "Nearest colposcopy" and ref["case"]["status"] == "REFERRAL_PENDING"
    created = next(e for e in events(client, org) if e["eventType"] == "REFERRAL_CREATED")
    assert created["actorRole"] == "REFERRING_CLINICIAN"
    err(submit(client, org, "REFERRAL_TARGET", {"receivingFacilityId": "nope", "rationale": "x"}), 404)

# ---------- intake ----------

def test_intake_creates_a_case_only_after_staff_approve(client, org):
    ids = org["ids"]
    payload = {"patientId": ids["pa"], "caseId": "NEW-1", "facilityId": ids["fa"], "priority": "HIGH", "nextActionCode": "CALL", "nextActionLabel": "Call patient"}
    err(submit(client, org, "INTAKE", payload, case="CA"), 422, "CASE_NOT_ALLOWED")
    err(submit(client, org, "INTAKE", {**payload, "facilityId": None}, case=None), 422, "INVALID_FACILITY")
    s = sub_ok(client, org, "INTAKE", payload, case=None)
    nums = lambda: {c["caseId"] for c in client.get("/api/cases", headers=org["auth"]("national")).json()["data"]}
    assert "NEW-1" not in nums()
    err(decide(client, org, s["id"], who="coordB"), 404)
    err(decide(client, org, s["id"], who="fadmin"), 403)
    d = decide(client, org, s["id"]).json()["data"]
    assert "NEW-1" in nums() and d["caseId"] == d["applied"]["caseId"]
    case = next(c for c in client.get("/api/cases", headers=org["auth"]("coord")).json()["data"] if c["caseId"] == "NEW-1")
    assert case["caseId"] == "NEW-1" and case["priority"] == "HIGH"
    ev = client.get(f"/api/cases/{d['caseId']}/events", headers=org["auth"]("coord")).json()["data"]
    assert [e["eventType"] for e in ev].count("CASE_TRANSITION") >= 2
    assert ev[0]["eventType"] == "CASE_TRANSITION"
    assert ev[0]["actorRole"] == "COORDINATOR"
    dup = sub_ok(client, org, "INTAKE", payload, case=None)
    err(decide(client, org, dup["id"]), 409, "DUPLICATE_CASE_ID")
    assert client.get(f"/api/ai/suggestions/{dup['id']}", headers=org["auth"]("coord")).json()["data"]["status"] == "PENDING"

# ---------- messages: approval gate (R-28) ----------

def draft(client, org, who="coord", body="Please call the clinic."):
    return client.post("/api/messages", headers=org["auth"](who), json={"caseId": "CA", "channel": "SMS", "body": body})

def send(client, org, mid, who="coord"):
    return client.post(f"/api/messages/{mid}/send", headers=org["auth"](who))

def approve(client, org, mid, who="coord", body=None):
    return client.post(f"/api/messages/{mid}/approve", headers=org["auth"](who), json=body or {})

def test_nothing_is_sent_without_approval(client, org):
    m = draft(client, org).json()["data"]
    assert m["status"] == "DRAFT" and m["approvedById"] is None
    err(send(client, org, m["id"]), 409, "MESSAGE_NOT_APPROVED")
    assert events(client, org)[-1]["eventType"] == "INVALID_ACTION_REJECTED"
    assert client.get(f"/api/messages/{m['id']}", headers=org["auth"]("coord")).json()["data"]["attempts"] == 0
    err(approve(client, org, m["id"], "recv"), 404); err(approve(client, org, m["id"], "fadmin"), 403); err(approve(client, org, m["id"], "coordB"), 404)
    a = approve(client, org, m["id"], body={"editedBody": "Please call us today."}).json()["data"]
    assert a["status"] == "APPROVED" and a["approvedById"] == org["ids"]["coord"] and a["body"] == "Please call us today."
    err(approve(client, org, m["id"]), 409, "INVALID_MESSAGE_STATE")
    s = send(client, org, m["id"]).json()["data"]
    assert s["status"] == "SENT" and s["attempts"] == 1 and s["sentAt"]
    err(send(client, org, m["id"]), 409, "MESSAGE_NOT_APPROVED")                                         # cannot be sent twice

def test_rejected_message_cannot_be_sent(client, org):
    m = draft(client, org).json()["data"]
    err(client.post(f"/api/messages/{m['id']}/reject", headers=org["auth"]("coord"), json={}), 422, "VALIDATION_ERROR")
    assert client.post(f"/api/messages/{m['id']}/reject", headers=org["auth"]("coord"), json={"reason": "Wrong tone"}).json()["data"]["status"] == "REJECTED"
    err(send(client, org, m["id"]), 409, "MESSAGE_NOT_APPROVED")

def test_message_permissions_and_visibility(client, org):
    for who, status in (("fadmin", 403), ("patient", 403), ("ai", 403), ("recv", 404), ("coordB", 404)):
        err(draft(client, org, who), status)
    m = draft(client, org).json()["data"]
    lst = lambda who: client.get("/api/messages", headers=org["auth"](who)).json()["meta"]["total"]
    assert lst("coord") == 1 and lst("coordB") == 0
    err(client.get(f"/api/messages/{m['id']}", headers=org["auth"]("coordB")), 404)
    err(client.get("/api/messages", headers=org["auth"]("fadmin")), 403)

def test_ai_message_draft_is_approved_by_staff_then_sent(client, org):
    s = sub_ok(client, org, "MESSAGE_DRAFT", {"channel": "EMAIL", "body": "Your appointment is due.", "purpose": "reminder"})
    assert client.get("/api/messages", headers=org["auth"]("coord")).json()["meta"]["total"] == 0           # a suggestion is not a message
    d = decide(client, org, s["id"], body={"editedBody": "Your appointment is due soon."}).json()["data"]
    m = client.get(f"/api/messages/{d['applied']['messageId']}", headers=org["auth"]("coord")).json()["data"]
    assert m["source"] == "AI_SUGGESTION" and m["status"] == "APPROVED" and m["approvedById"] == org["ids"]["coord"] and m["body"] == "Your appointment is due soon."
    assert send(client, org, m["id"]).json()["data"]["status"] == "SENT"

# ---------- messages: retries and alerts (R-19) ----------

class Failing:
    def __init__(self, fail_times): self.left = fail_times; self.calls = 0
    def send(self, message):
        self.calls += 1
        if self.left > 0:
            self.left -= 1; raise RuntimeError("gateway timeout")

def make_due(client, mid):
    db = client.session_factory(); db.get(Message, mid).next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit(); db.close()

def process(client, org, who="coord"):
    return client.post("/api/messages/process-due", headers=org["auth"](who))

def approved(client, org):
    m = draft(client, org).json()["data"]; approve(client, org, m["id"]); return m["id"]

def test_failed_message_is_retried_then_marked_failed_and_staff_alerted(client, org):
    provider = Failing(99); app.dependency_overrides[get_message_provider] = lambda: provider
    mid = approved(client, org)
    m = send(client, org, mid).json()["data"]
    assert m["status"] == "RETRYING" and m["attempts"] == 1 and m["nextRetryAt"] and m["lastError"] == "gateway timeout"
    assert process(client, org).json()["data"]["processed"] == 0                                    # not due yet
    make_due(client, mid); assert process(client, org).json()["data"] == {"processed": 1, "sent": 0, "retrying": 1, "failed": 0}
    make_due(client, mid); assert process(client, org).json()["data"] == {"processed": 1, "sent": 0, "retrying": 1, "failed": 0}
    make_due(client, mid); assert process(client, org).json()["data"] == {"processed": 1, "sent": 0, "retrying": 0, "failed": 1}
    m = client.get(f"/api/messages/{mid}", headers=org["auth"]("coord")).json()["data"]
    assert m["status"] == "MESSAGE_FAILED" and m["attempts"] == 4 and m["nextRetryAt"] is None and provider.calls == 4
    alerts = client.get("/api/tasks?type=MESSAGE_FAILED&status=OPEN", headers=org["auth"]("coord")).json()["data"]
    assert len(alerts) == 1 and alerts[0]["caseId"] == org["ids"]["ca"]
    types = [e["eventType"] for e in events(client, org)]
    assert types.count("MESSAGE_SEND_FAILED") == 3 and types.count("MESSAGE_FAILED") == 1
    assert process(client, org).json()["data"]["processed"] == 0                                    # no further automatic retries
    err(send(client, org, mid), 409, "MESSAGE_NOT_APPROVED")

def test_retry_can_succeed(client, org):
    provider = Failing(1); app.dependency_overrides[get_message_provider] = lambda: provider
    mid = approved(client, org)
    assert send(client, org, mid).json()["data"]["status"] == "RETRYING"
    make_due(client, mid)
    assert process(client, org).json()["data"]["sent"] == 1
    m = client.get(f"/api/messages/{mid}", headers=org["auth"]("coord")).json()["data"]
    assert m["status"] == "SENT" and m["attempts"] == 2 and m["lastError"] is None
    assert client.get("/api/tasks?type=MESSAGE_FAILED", headers=org["auth"]("coord")).json()["data"] == []

def test_process_due_is_role_and_scope_limited(client, org):
    provider = Failing(1); app.dependency_overrides[get_message_provider] = lambda: provider
    mid = approved(client, org); send(client, org, mid); make_due(client, mid)
    for who in ("refer", "recv", "fadmin", "ai"): err(process(client, org, who), 403)
    assert process(client, org, "coordB").json()["data"]["processed"] == 0                         # other facility's messages are out of scope
    assert process(client, org, "national").json()["data"]["processed"] == 1
