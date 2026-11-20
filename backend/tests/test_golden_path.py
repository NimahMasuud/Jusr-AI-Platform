from app.core import clock

def case_status(d, case, who="coord"):
    return d.call(who, "GET", f"/cases/{case}")

def test_referral_route_end_to_end(d):
    r = d.feed("E1", "hc", patient={"name": "Patient 001", "birthYear": None, "recordNumber": "MRN00001"}, case_number="C-1", confirmatory=False)
    assert r["status"] == "ACCEPTED", r
    # name + record number = two identifiers: high confidence, so T1 and T2 ran
    assert r["caseStatus"] == "AWAITING_CLASSIFICATION" and r["trackerId"].startswith("JU-")
    d.call("refer", "POST", "/cases/C-1/classify", json={"actionable": True, "urgent": False})
    assert case_status(d, "C-1")["status"] == "NOTIFYING"
    d.notify("C-1")
    assert case_status(d, "C-1")["status"] == "AWAITING_ACK"
    tok = d.patient_link("C-1")
    d.patient_replies(tok, understood="YES", confidence=5, case="C-1")
    d.call("refer", "POST", "/referrals", json={"caseId": "C-1", "receivingFacilityId": d.ids["rrh"], "targetSpecialty": "COLPOSCOPY", "reason": "Abnormal HPV"})
    c = case_status(d, "C-1"); assert c["status"] == "REFERRAL_PENDING"
    ref = d.call("recv", "GET", "/referrals")[0]
    d.call("recv", "POST", f"/referrals/{ref['id']}/accept", json={})
    assert case_status(d, "C-1", "recv")["status"] == "AWAITING_APPOINTMENT"
    appt = d.call("coordR", "POST", "/cases/C-1/appointments", json={"scheduledAt": "2030-01-01T09:00:00Z"})
    d.call("coordR", "POST", f"/cases/C-1/appointments/{appt['id']}/attendance", json={"attendance": "ATTENDED"})
    assert case_status(d, "C-1", "recv")["status"] == "AWAITING_TREATMENT"
    d.call("recv", "POST", "/cases/C-1/treatment-start", json={"kind": "TREATMENT", "startDate": "2030-01-10T00:00:00Z", "note": "LLETZ done"})
    assert case_status(d, "C-1", "recv")["status"] == "READY_TO_CLOSE"
    d.call("coord", "POST", "/cases/C-1/close", json={"closureType": "CARE_CONFIRMED", "reason": "Treatment started"})
    assert case_status(d, "C-1")["status"] == "CLOSED"
