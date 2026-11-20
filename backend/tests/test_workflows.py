"""Scheduler jobs, urgent routing deadlines, referral time-outs, consultations, patient links and AI approvals."""
import pytest
from app.core import clock
from app.scheduler import run_once

def new_case(d, n="C-1", idx=1, confirmatory=False):
    return d.feed(f"E-{n}", "hc", patient={"name": f"Patient {idx:03d}", "recordNumber": f"MRN{idx:05d}"}, case_number=n, confirmatory=confirmatory)

def to_ack(d, n="C-1", idx=1, **kw):
    new_case(d, n, idx, **kw); d.call("refer", "POST", f"/cases/{n}/classify", json={"actionable": True}); d.notify(n)
    d.patient_replies(d.patient_link(n), case=n)

def sched(d):
    return run_once(d.c.session_factory)

# ---------------------------------------------------------------- urgent routing (R-13, R-14)

def urgent(d, n="C-1", idx=1):
    new_case(d, n, idx); d.call("refer", "POST", f"/cases/{n}/classify", json={"actionable": True, "urgent": True, "specialty": "COLPOSCOPY"})

def test_urgent_case_escalates_then_reroutes_then_becomes_an_exception(d):
    urgent(d)
    d.wait(minutes=130); sched(d)
    stage1 = d.call("coord", "GET", "/cases/C-1/urgent-routing")["routing"]
    assert stage1["stage"] == 1
    d.wait(minutes=130); sched(d)
    assert d.call("coord", "GET", "/cases/C-1/urgent-routing")["routing"]["stage"] == 2     # a backup was offered the case
    d.wait(minutes=260); sched(d)
    c = d.call("coord", "GET", "/cases/C-1")
    assert "EXCEPTION" in c["flags"]

def test_only_a_matching_specialty_can_accept(d):
    urgent(d)
    r = d.c.post("/api/v1/urgent-cases/C-1/accept", headers=d.auth("recv3"))
    assert r.status_code in (403, 404)

# ---------------------------------------------------------------- referral time-out (R-46)

def test_referral_not_accepted_in_time_sets_exception(d):
    to_ack(d)
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY"})
    d.wait(days=4); sched(d)
    assert d.call("coord", "GET", "/cases/C-1")["status"] == "REFERRAL_PENDING"
    d.wait(days=4); sched(d)
    c = d.call("coord", "GET", "/cases/C-1")
    assert c["status"] == "REFERRAL_PENDING" and "EXCEPTION" in c["flags"]
    rid = d.call("refer", "GET", "/referrals", params={"caseId": "C-1"})[0]
    assert rid["status"] == "NOT_ACCEPTED_IN_TIME"

# ---------------------------------------------------------------- consultations (R-49 to R-51)

def test_consultation_requires_an_outcome_type_and_note(d):
    to_ack(d)
    k = d.call("refer", "POST", "/consultations", json={"caseId": "C-1", "type": "CLINICIAN_TO_CLINICIAN", "recipientSpecialty": "colposcopy", "question": "Advice?"})
    assert k["state"] == "REQUESTED"
    d.call("recv", "POST", f"/consultations/{k['id']}/accept")
    r = d.c.post(f"/api/v1/consultations/{k['id']}/outcome", headers=d.auth("recv"), json={"outcomeType": "ADVICE_GIVEN"})
    assert r.status_code == 422
    done = d.call("recv", "POST", f"/consultations/{k['id']}/outcome", json={"outcomeType": "ADVICE_GIVEN", "note": "Refer directly"})
    assert done["state"] == "OUTCOME_RECORDED"

def test_unaccepted_consultation_escalates_after_its_limit(d):
    to_ack(d)
    k = d.call("refer", "POST", "/consultations", json={"caseId": "C-1", "type": "CLINICIAN_TO_CLINICIAN", "recipientSpecialty": "COLPOSCOPY", "question": "Advice?"})
    d.wait(days=3); sched(d)
    assert d.call("refer", "GET", f"/consultations/{k['id']}")["state"] == "ESCALATED"

def test_patient_callback_request_creates_a_consultation_for_the_owner(d):
    to_ack(d)
    tok = d.patient_link("C-1")
    from app.demo_data import BIRTH_YEARS
    pid = d.call("coord", "GET", "/cases/C-1")["patientId"]
    sess = d.c.post(f"/p/{tok}/verify", json={"birthYear": BIRTH_YEARS[pid]}).json()["data"]["sessionToken"]
    r = d.c.post(f"/p/{tok}/callback", json={"preferredTime": "Morning"}, headers={"X-Patient-Session": sess})
    assert r.status_code in (200, 201), r.text
    ks = d.call("coord", "GET", "/consultations", params={"type": "PATIENT_CALLBACK"})
    assert len(ks) == 1 and ks[0]["copiedToCoordinator"]

# ---------------------------------------------------------------- patient link (R-31, R-36)

def test_wrong_birth_year_locks_the_link_after_three_tries(d):
    new_case(d); d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True})
    tok = d.patient_link("C-1")
    for _ in range(3):
        assert d.c.post(f"/p/{tok}/verify", json={"birthYear": 1900}).status_code in (400, 401, 403, 422, 423)
    assert d.c.post(f"/p/{tok}/verify", json={"birthYear": 1900}).status_code in (403, 423, 429)

def test_a_new_link_cancels_the_old_one(d):
    new_case(d); d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True})
    t1 = d.patient_link("C-1"); t2 = d.patient_link("C-1")
    assert d.c.get(f"/p/{t1}").status_code in (403, 404, 410)
    assert t1 != t2

def test_staff_assisted_response_is_attributed_to_staff(d):
    new_case(d, confirmatory=True); d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True}); d.notify("C-1")
    d.call("coord", "POST", "/cases/C-1/assisted-responses", json={"acknowledged": True, "understood": "YES", "confidence": 4, "explanationStatus": "EXPLAINED", "callbackRequested": False})
    assert d.call("coord", "GET", "/cases/C-1")["status"] == "AWAITING_CONFIRMATION"          # T8 by staff phone confirmation
    rs = d.call("coord", "GET", "/cases/C-1/patient-responses")
    assert all(r["source"] == "STAFF_ASSISTED" for r in rs)

# ---------------------------------------------------------------- messages (R-19, R-28)

def test_message_must_be_approved_before_sending_and_failures_set_the_flag(d):
    new_case(d); d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True})
    m = d.call("coord", "POST", "/messages", json={"caseId": "C-1", "channel": "SMS", "body": "Your result is ready."})
    r = d.c.post(f"/api/v1/messages/{m['id']}/send", headers=d.auth("coord"))
    assert r.status_code == 409
    assert d.call("coord", "GET", "/cases/C-1")["status"] == "NOTIFYING"

# ---------------------------------------------------------------- AI suggestions (R-28)

def test_ai_intake_needs_a_coordinator_to_approve_and_creates_a_case(d):
    s = d.call("ai", "POST", "/ai/suggestions", json={"kind": "INTAKE", "payload": {"patientId": d.ids["patients"][0], "caseId": "AI-1", "facilityId": d.ids["hc"]}})
    assert d.c.post(f"/api/v1/ai/suggestions/{s['id']}/approve", headers=d.auth("refer"), json={}).status_code == 403
    d.call("coord", "POST", f"/ai/suggestions/{s['id']}/approve", json={})
    c = d.call("coord", "GET", "/cases/AI-1")
    assert c["status"] in ("NEW", "AWAITING_CLASSIFICATION")

def test_ai_cannot_change_the_status_on_its_own(d):
    new_case(d)
    s = d.call("ai", "POST", "/ai/suggestions", json={"kind": "URGENCY", "caseId": "C-1", "payload": {"priority": "URGENT", "actionability": "ACTIONABLE", "rationale": "High risk"}})
    assert d.call("coord", "GET", "/cases/C-1")["status"] == "AWAITING_CLASSIFICATION"
    assert d.c.post(f"/api/v1/ai/suggestions/{s['id']}/approve", headers=d.auth("coord"), json={}).status_code == 403   # a coordinator does not set urgency
