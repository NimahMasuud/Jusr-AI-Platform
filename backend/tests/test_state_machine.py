"""The state machine: allowed moves, refused moves and the guards (Part 1 section 3, R-12, A-06)."""
import pytest
from app.core import clock

def status(d, case, who="national"):
    return d.call(who, "GET", f"/cases/{case}")["status"]

def refused(d, who, method, path, code, http=(403, 409, 422), **kw):
    r = d.c.request(method, "/api/v1" + path, headers=d.auth(who), **kw)
    assert r.status_code in http, r.text
    assert r.json()["error"]["code"] == code, r.text
    return r

def new_case(d, n="C-1", confirmatory=False, idx=1):
    d.feed(f"E-{n}", "hc", patient={"name": f"Patient {idx:03d}", "recordNumber": f"MRN{idx:05d}"}, case_number=n, confirmatory=confirmatory)

def test_table_has_17_transitions(d):
    t = d.call("coord", "GET", "/cases/transitions")
    assert [x["id"] for x in t["transitions"]] == [f"T{i}" for i in range(1, 18)]
    assert len(t["statuses"]) == 11

def test_no_direct_status_change(d):
    new_case(d)
    r = d.c.post("/api/v1/cases/C-1/transition", headers=d.auth("coord"), json={"status": "CLOSED"})
    assert r.status_code in (403, 404, 405)

def test_a_coordinator_cannot_classify(d):
    new_case(d)
    refused(d, "coord", "POST", "/cases/C-1/classify", "ROLE_NOT_ALLOWED", json={"actionable": True})
    assert status(d, "C-1") == "AWAITING_CLASSIFICATION"

def test_refused_move_is_logged_and_changes_nothing(d):
    new_case(d)
    r = d.c.post("/api/v1/referrals", headers=d.auth("refer"), json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"]})
    assert r.status_code == 409
    assert status(d, "C-1") == "AWAITING_CLASSIFICATION"
    ev = d.call("coord", "GET", "/cases/C-1/events")
    assert any(e["eventType"] == "INVALID_ACTION_REJECTED" for e in ev)

def test_confirmatory_case_waits_for_the_test(d):
    new_case(d, confirmatory=True)
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True})
    d.notify("C-1")
    d.patient_replies(d.patient_link("C-1"), case="C-1")
    assert status(d, "C-1") == "AWAITING_CONFIRMATION"     # T8

def test_partly_understood_sets_not_explained_and_holds_the_case(d):
    new_case(d, confirmatory=True)
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True})
    d.notify("C-1")
    d.patient_replies(d.patient_link("C-1"), understood="PARTLY", case="C-1")
    c = d.call("coord", "GET", "/cases/C-1")
    assert c["status"] == "AWAITING_ACK" and "NOT_EXPLAINED" in c["flags"]
    d.call("coord", "POST", "/cases/C-1/explained", json={"note": "Called the patient and explained"})
    assert "NOT_EXPLAINED" not in d.call("coord", "GET", "/cases/C-1")["flags"]

def test_urgent_needs_a_specialty_and_goes_through_routing(d):
    new_case(d)
    refused(d, "refer", "POST", "/cases/C-1/classify", "SPECIALTY_REQUIRED", json={"actionable": True, "urgent": True})
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True, "urgent": True, "specialty": "colposcopy"})
    assert status(d, "C-1") == "URGENT_ROUTING"
    # only a clinician whose profile specialty matches can accept (R-13)
    routed = d.call("coord", "GET", "/cases/C-1/urgent-routing")["routing"]["routedClinician"]["id"]
    d.call("recv" if routed == d.ids["recv"] else "recv2", "POST", "/urgent-cases/C-1/accept", json={})
    assert status(d, "C-1") == "NOTIFYING"

def test_not_actionable_needs_a_reason_and_closes(d):
    new_case(d)
    r = d.c.post("/api/v1/cases/C-1/classify", headers=d.auth("refer"), json={"actionable": False})
    assert r.status_code == 422
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": False, "reason": "False alarm"})
    assert status(d, "C-1") == "CLOSED"

def test_closed_case_is_read_only(d):
    new_case(d)
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": False, "reason": "False alarm"})
    r = d.c.post("/api/v1/cases/C-1/classify", headers=d.auth("refer"), json={"actionable": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_CLOSED"

def test_decline_keeps_the_case_pending_with_exception_then_new_referral(d):
    new_case(d)
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True}); d.notify("C-1")
    d.patient_replies(d.patient_link("C-1"), case="C-1")
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY"})
    rid = d.call("recv", "GET", "/referrals")[0]["id"]
    r = d.c.post(f"/api/v1/referrals/{rid}/decline", headers=d.auth("recv"), json={})
    assert r.status_code == 422                                                      # a reason is required
    d.call("recv", "POST", f"/referrals/{rid}/decline", json={"code": "NO_CAPACITY", "reason": "Full"})
    c = d.call("coord", "GET", "/cases/C-1")
    assert c["status"] == "REFERRAL_PENDING" and "EXCEPTION" in c["flags"]
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY"})
    rid2 = d.call("recv2", "GET", "/referrals", params={"status": "SENT"})[0]["id"]
    d.call("recv2", "POST", f"/referrals/{rid2}/accept", json={})
    c = d.call("recv2", "GET", "/cases/C-1")
    assert c["status"] == "AWAITING_APPOINTMENT" and c["owner"]["id"] == d.ids["recv2"] and "EXCEPTION" not in c["flags"]

def test_missed_appointment_needs_a_reason_code_and_stays_put(d):
    new_case(d)
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True}); d.notify("C-1")
    d.patient_replies(d.patient_link("C-1"), case="C-1")
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY"})
    d.call("recv", "POST", f"/referrals/{d.call('recv', 'GET', '/referrals')[0]['id']}/accept", json={})
    a = d.call("coordR", "POST", "/cases/C-1/appointments", json={"scheduledAt": "2030-01-01T09:00:00Z"})
    r = d.c.post(f"/api/v1/cases/C-1/appointments/{a['id']}/attendance", headers=d.auth("coordR"), json={"attendance": "MISSED"})
    assert r.status_code == 422
    d.call("coordR", "POST", f"/cases/C-1/appointments/{a['id']}/attendance", json={"attendance": "MISSED", "reasonCode": "PATIENT_UNREACHABLE"})
    assert status(d, "C-1") == "AWAITING_APPOINTMENT"
    # R-47: a new booking is needed
    d.call("coordR", "POST", "/cases/C-1/appointments", json={"scheduledAt": "2030-02-01T09:00:00Z"})

def test_treatment_start_needs_a_record(d):
    new_case(d)
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True}); d.notify("C-1")
    d.patient_replies(d.patient_link("C-1"), case="C-1")
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY"})
    d.call("recv", "POST", f"/referrals/{d.call('recv', 'GET', '/referrals')[0]['id']}/accept", json={})
    a = d.call("coordR", "POST", "/cases/C-1/appointments", json={"scheduledAt": "2030-01-01T09:00:00Z"})
    d.call("coordR", "POST", f"/cases/C-1/appointments/{a['id']}/attendance", json={"attendance": "ATTENDED"})
    r = d.c.post("/api/v1/cases/C-1/treatment-start", headers=d.auth("recv"), json={"kind": "TREATMENT", "startDate": "2030-01-10T00:00:00Z"})
    assert r.status_code in (409, 422)
    assert status(d, "C-1") == "AWAITING_TREATMENT"
