"""Closure rules, time limits and the demo clock, settings, events, measures, access and the audit log."""
import csv, io
from datetime import timedelta
import pytest
from app.core import clock

def new_case(d, n="C-1", confirmatory=False, idx=1):
    return d.feed(f"E-{n}", "hc", patient={"name": f"Patient {idx:03d}", "recordNumber": f"MRN{idx:05d}"}, case_number=n, confirmatory=confirmatory)

def to_notifying(d, n="C-1", **kw):
    new_case(d, n, **kw); d.call("refer", "POST", f"/cases/{n}/classify", json={"actionable": True})

def err(r): return r.json()["error"]["code"]

# ---------------------------------------------------------------- closure (A-01, R-15, R-53)

def test_system_never_closes_and_closing_needs_evidence(d):
    to_notifying(d)
    # the checklist lists what is missing before closure
    cl = d.call("coord", "GET", "/cases/C-1/closure-checklist", params={"closureType": "NO_FURTHER_CARE"})
    assert cl["complete"] is False and any(not i["present"] for i in cl["items"])
    r = d.c.post("/api/v1/cases/C-1/close", headers=d.auth("coord"), json={"closureType": "CARE_CONFIRMED", "reason": "x"})
    assert r.status_code in (403, 409, 422)
    assert d.call("coord", "GET", "/cases/C-1")["status"] == "NOTIFYING"

def test_care_confirmed_only_from_ready_to_close(d):
    to_notifying(d)
    d.call("coord", "POST", "/cases/C-1/assign", json={"ownerId": d.ids["refer"]})
    r = d.c.post("/api/v1/cases/C-1/close", headers=d.auth("refer"), json={"closureType": "CARE_CONFIRMED", "reason": "x"})
    assert r.status_code in (409, 422)

def test_unreachable_needs_attempts_on_two_routes(d):
    to_notifying(d)
    d.call("coord", "POST", "/cases/C-1/assign", json={"ownerId": d.ids["refer"]})
    body = {"closureType": "UNREACHABLE", "reason": "No answer", "decision": "Close as unreachable", "evidence": "attempts"}
    r = d.c.post("/api/v1/cases/C-1/close", headers=d.auth("refer"), json=body)
    assert r.status_code == 422 and err(r) == "EVIDENCE_REQUIRED"
    d.wait(days=8)
    for route in ("PHONE", "PHONE", "SMS"):
        d.call("coord", "POST", "/cases/C-1/contact-attempts", json={"route": route, "outcome": "NOT_REACHED"})
    d.call("refer", "POST", "/cases/C-1/close", json=body)
    assert d.call("refer", "GET", "/cases/C-1")["status"] == "CLOSED"

def test_a_coordinator_cannot_make_a_clinical_closure(d):
    to_notifying(d)
    r = d.c.post("/api/v1/cases/C-1/close", headers=d.auth("coord2"), json={"closureType": "NO_FURTHER_CARE", "reason": "x", "decision": "x"})
    assert r.status_code == 403

# ---------------------------------------------------------------- time limits, OVERDUE, demo clock (R-66, R-18, A-10)

def test_overdue_appears_when_the_demo_clock_moves_and_needs_a_reason_code(d):
    to_notifying(d)                                            # NOTIFYING limit: 1 working day
    assert "OVERDUE" not in d.call("coord", "GET", "/cases/C-1")["flags"]
    adv = d.call("national", "POST", "/demo/clock/advance", json={"minutes": 5 * 24 * 60})
    assert adv["active"] and adv["banner"]
    c = d.call("coord", "GET", "/cases/C-1")
    assert "OVERDUE" in c["flags"]
    wl = d.call("coord", "GET", "/worklist", params={"tab": "OVERDUE"})
    assert wl["total"] == 1
    r = d.c.post("/api/v1/cases/C-1/delay-reason", headers=d.auth("coord"), json={"code": "OTHER"})
    assert r.status_code == 422                                 # OTHER needs a note
    d.call("coord", "POST", "/cases/C-1/delay-reason", json={"code": "NO_SLOT_AVAILABLE"})
    assert "OVERDUE" not in d.call("coord", "GET", "/cases/C-1")["flags"]
    d.call("national", "POST", "/demo/clock/reset")
    assert not clock.is_active()

def test_demo_clock_is_for_the_national_admin_only(d):
    r = d.c.post("/api/v1/demo/clock/advance", headers=d.auth("coord"), json={"minutes": 5})
    assert r.status_code == 403

def test_the_status_limit_is_a_setting_and_a_change_takes_effect_at_once(d):
    to_notifying(d)
    d.wait(hours=6)
    assert "OVERDUE" not in d.call("coord", "GET", "/cases/C-1")["flags"]           # default limit: 1 working day
    d.call("national", "PUT", "/settings/limit.NOTIFYING", json={"value": {"value": 2, "unit": "hours"}, "scope": "global"})
    assert "OVERDUE" in d.call("coord", "GET", "/worklist", params={"tab": "OVERDUE"})["cases"][0]["flags"]   # applies to the case already waiting
    d.call("national", "DELETE", "/settings/limit.NOTIFYING", params={"scope": "global"})

def test_a_coordinator_cannot_change_settings(d):
    r = d.c.put("/api/v1/settings/limit.NOTIFYING", headers=d.auth("coord"), json={"value": {"value": 1, "unit": "hours"}})
    assert r.status_code == 403

def test_invalid_setting_is_refused(d):
    r = d.c.put("/api/v1/settings/limit.NOTIFYING", headers=d.auth("national"), json={"value": {"value": -1, "unit": "hours"}})
    assert r.status_code == 422

# ---------------------------------------------------------------- events (A-11 to A-13)

def test_duplicate_event_changes_nothing_and_is_logged(d):
    first = new_case(d)
    assert first["status"] == "ACCEPTED"
    again = d.call("coord", "POST", "/events", json={"eventId": "E-C-1", "type": "RESULT_RECEIVED", "facilityId": d.ids["hc"], "payload": {}})
    assert again["status"] == "DUPLICATE"
    assert d.call("coord", "GET", "/cases")  # still one case
    assert len(d.call("coord", "GET", "/cases")) == 1

def test_invalid_events_are_refused_logged_and_listed(d):
    bad = d.c.post("/api/v1/events", headers=d.auth("coord"), json={"eventId": "B1", "type": "RESULT_RECEIVED", "facilityId": d.ids["hc"],
                                                                   "payload": {"patient": {"name": "Patient 001", "recordNumber": "MRN00001"}, "test": {"code": "", "value": ""}}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "UNREADABLE_RESULT"
    assert d.call("coord", "GET", "/cases") == []
    rej = d.call("coord", "GET", "/events/rejected")
    assert len(rej) == 1 and rej[0]["errorCode"] == "UNREADABLE_RESULT"
    counts = d.call("admin", "GET", "/events/rejected")
    assert counts["total"] == 1 and "payload" not in str(counts)              # facility admin: counts only (R-09)

def test_weak_match_waits_for_a_coordinator(d):
    r = d.feed("W1", "hc", patient={"name": "Patient 001"}, case_number="C-W")
    assert r["caseStatus"] == "NEW"
    d.call("coord", "POST", "/cases/C-W/confirm-match", json={})
    assert d.call("coord", "GET", "/cases/C-W")["status"] == "AWAITING_CLASSIFICATION"

def test_a_coordinator_cannot_send_events_for_another_facility(d):
    r = d.c.post("/api/v1/events", headers=d.auth("coord"), json={"eventId": "X", "type": "TEST_EVENT", "facilityId": d.ids["dc"], "payload": {}})
    assert r.status_code == 422

def test_missing_feed_sets_data_missing_and_the_next_event_clears_it(d):
    new_case(d)
    d.call("national", "POST", "/events", json={"eventId": "G1", "type": "FEED_MISSING", "facilityId": d.ids["hc"], "payload": {}})
    assert "DATA_MISSING" in d.call("coord", "GET", "/cases/C-1")["flags"]
    d.call("coord", "POST", "/events", json={"eventId": "T1", "type": "TEST_EVENT", "facilityId": d.ids["hc"], "payload": {}})
    assert "DATA_MISSING" not in d.call("coord", "GET", "/cases/C-1")["flags"]

# ---------------------------------------------------------------- tracker id, audit log

def test_tracker_id_check_character(d):
    from app.services import tracker
    t = new_case(d)["trackerId"]
    assert t.startswith("JU-") and tracker.is_valid(t)
    assert not tracker.is_valid(t[:-1] + ("2" if t[-1] != "2" else "3"))

def test_every_transition_is_in_the_audit_log_with_its_t_id(d):
    to_notifying(d)
    ev = d.call("coord", "GET", "/cases/C-1/events")
    ts = [e["newValues"].get("transition") for e in ev if e["eventType"] == "CASE_TRANSITION"]
    assert ts == ["T1", "T2", "T3"] or sorted(ts) == ["T1", "T2", "T3"]

def test_audit_log_cannot_be_changed(d):
    to_notifying(d)
    from app.models.entities import AuditEvent
    db = d.c.session_factory()
    e = db.query(AuditEvent).first()
    e.description = "tampered"
    with pytest.raises(Exception):
        db.commit()
    db.rollback()
    with pytest.raises(Exception):
        db.delete(e); db.commit()
    db.close()

# ---------------------------------------------------------------- access (R-52, Part 1 matrix)

def test_facility_admin_sees_no_cases_and_other_facilities_are_hidden(d):
    new_case(d)
    assert d.c.get("/api/v1/cases", headers=d.auth("admin")).status_code == 403
    assert d.call("coordR", "GET", "/cases") == []
    assert d.c.get("/api/v1/cases/C-1", headers=d.auth("coordR")).status_code == 404

def test_only_a_coordinator_sends_messages(d):
    to_notifying(d)
    r = d.c.post("/api/v1/messages", headers=d.auth("refer"), json={"caseId": "C-1", "channel": "SMS", "body": "hello"})
    assert r.status_code == 403

def test_receiving_clinician_sees_the_case_only_after_accepting(d):
    to_notifying(d); d.notify("C-1"); d.patient_replies(d.patient_link("C-1"), case="C-1")
    assert d.c.get("/api/v1/cases/C-1", headers=d.auth("recv")).status_code == 404
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY"})
    rid = d.call("recv", "GET", "/referrals")[0]["id"]
    d.call("recv", "POST", f"/referrals/{rid}/accept", json={})
    assert d.c.get("/api/v1/cases/C-1", headers=d.auth("recv")).status_code == 200

# ---------------------------------------------------------------- measures (A-22): recompute from the exported log

def test_measures_match_the_event_log_export(d):
    for i in range(1, 5):
        n = f"C-{i}"; new_case(d, n, idx=i); d.call("refer", "POST", f"/cases/{n}/classify", json={"actionable": True}); d.wait(minutes=10 * i); d.notify(n); d.wait(minutes=5)
    m = d.call("national", "GET", "/measures")
    n_notified = m["m1"]["resultToNotified"]["n"]
    csv_text = d.c.get("/api/v1/events/export", headers=d.auth("national"), params={"format": "csv"}).text
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    t7 = [r for r in rows if r["transition"] == "T7"]
    assert n_notified == len(t7) == 4
    by_case = {}
    for r in rows:
        if r["transition"] in ("T1", "T7"): by_case.setdefault(r["caseId"], {})[r["transition"]] = r["time"]
    from datetime import datetime
    hrs = sorted((datetime.fromisoformat(v["T7"]) - datetime.fromisoformat(v["T1"])).total_seconds() / 3600 for v in by_case.values())
    median = (hrs[1] + hrs[2]) / 2
    assert abs(m["m1"]["resultToNotified"]["medianHours"] - median) < 0.01
