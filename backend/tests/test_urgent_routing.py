from datetime import datetime, timedelta, timezone
import pytest
from app.models.entities import Case, CaseStatus, User

def err(r, status, code=None):
    assert r.status_code == status, r.text
    assert r.json()["success"] is False
    if code: assert r.json()["error"]["code"] == code

@pytest.fixture()
def spec(client, org):
    """recv (A) and recvB (B) are colposcopists; recvB2 (B) is a surgeon; recvC has no specialty."""
    db = client.session_factory()
    for key, value in {"recv": "COLPOSCOPY", "recvB": "COLPOSCOPY", "recvB2": "SURGERY"}.items():
        db.get(User, org["ids"][key]).specialty = value
    # This module tests the urgent-routing API after T4. The shared `org`
    # fixture's CA is intentionally AWAITING_ACK for patient-link tests.
    case = db.get(Case, org["ids"]["ca"])
    case.status = CaseStatus.URGENT_ROUTING
    db.commit(); db.close()

def route(client, org, who="coord", case="ca", **body):
    return client.post(f"/api/cases/{org['ids'][case]}/urgent-routing", headers=org["auth"](who), json=body)

def state(client, org, who="coord", case="ca"):
    return client.get(f"/api/cases/{org['ids'][case]}/urgent-routing", headers=org["auth"](who)).json()["data"]["routing"]

def mine(client, org, who, q=""):
    return client.get(f"/api/urgent-cases{q}", headers=org["auth"](who))

def accept(client, org, who, case="ca"):
    return client.post(f"/api/urgent-cases/{org['ids'][case]}/accept", headers=org["auth"](who))

def process(client, org, who="coord"):
    return client.post("/api/urgent-cases/process-due", headers=org["auth"](who))

def make_due(client, org, case="ca"):
    db = client.session_factory(); db.get(Case, org["ids"][case]).routing_due_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit(); db.close()

def events(client, org, case="ca"):
    return client.get(f"/api/cases/{org['ids'][case]}/events", headers=org["auth"]("national")).json()["data"]

def types(client, org, case="ca"):
    return [e["eventType"] for e in events(client, org, case)]

def open_tasks(client, org, type):
    return client.get(f"/api/tasks?type={type}&status=OPEN", headers=org["auth"]("coord")).json()["data"]

# ---------- routing and the clinician's own list ----------

def test_route_picks_a_qualified_clinician_and_lists_it_for_them_only(client, org, spec):
    r = route(client, org, specialty="colposcopy")                           # normalised to COLPOSCOPY
    assert r.status_code == 200, r.text
    st = r.json()["data"]["routing"]
    assert st["status"] == "AWAITING_ACCEPTANCE" and st["stage"] == 0 and st["requiredSpecialty"] == "COLPOSCOPY"
    assert st["routedClinician"]["id"] == org["ids"]["recv"]                  # same-facility clinician preferred
    assert st["firstLimitMinutes"] == 120 and st["secondLimitMinutes"] == 120   # defaults from settings_store
    due = datetime.fromisoformat(st["dueAt"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
    assert timedelta(minutes=119) < due <= timedelta(minutes=120, seconds=5)
    ev = events(client, org)[-1]
    assert ev["eventType"] == "URGENT_CASE_ROUTED" and ev["actorRole"] == "COORDINATOR" and ev["actorId"] == org["ids"]["coord"]
    item = mine(client, org, "recv").json()["data"][0]
    assert item["caseId"] == "CA" and item["patientLabel"] == "PA" and item["specialty"] == "COLPOSCOPY" and item["routingStatus"] == "AWAITING_ACCEPTANCE"
    assert {"age", "sex", "screening", "facility", "nextAction", "routingDueAt"} <= set(item)
    for who in ("recvB", "recvB2", "recvC"): assert mine(client, org, who).json()["data"] == []
    for who in ("coord", "refer", "fadmin", "ai", "national", "patient"): err(mine(client, org, who), 403)

def test_route_validation_and_permissions(client, org, spec):
    ids = org["ids"]
    # This test verifies the missing-specialty validation specifically.
    # The shared fixture seeds CA with COLPOSCOPY for the other routing tests.
    db = client.session_factory()
    case = db.get(Case, ids["ca"])
    original_specialty = case.required_specialty
    case.required_specialty = None
    db.commit(); db.close()
    err(route(client, org), 422, "SPECIALTY_REQUIRED")
    db = client.session_factory()
    db.get(Case, ids["ca"]).required_specialty = original_specialty
    db.commit(); db.close()
    err(route(client, org, specialty="COLPOSCOPY", receivingClinicianId=ids["recvB2"]), 422, "SPECIALTY_MISMATCH")
    err(route(client, org, specialty="COLPOSCOPY", receivingClinicianId=ids["coord"]), 422, "INVALID_ASSIGNEE")
    err(route(client, org, specialty="COLPOSCOPY", receivingClinicianId="nope"), 404)
    err(route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=0), 422, "VALIDATION_ERROR")
    err(route(client, org, who="coordB", specialty="COLPOSCOPY", case="cb"), 409, "CASE_NOT_URGENT")      # CB is NORMAL priority
    assert types(client, org, "cb")[-1] == "INVALID_ACTION_REJECTED"
    for who, status in (("fadmin", 403), ("patient", 403), ("ai", 403), ("recv", 404), ("coordB", 404)):
        err(route(client, org, who, specialty="COLPOSCOPY"), status)
    assert route(client, org, "refer", specialty="COLPOSCOPY").status_code == 200
    err(route(client, org, specialty="COLPOSCOPY"), 409, "ROUTING_ALREADY_ACTIVE")
    closed = client.session_factory(); closed.get(Case, ids["cb"]).status = CaseStatus.CLOSED; closed.commit(); closed.close()

def test_closed_case_cannot_be_routed(client, org, spec):
    db = client.session_factory(); db.get(Case, org["ids"]["ca"]).status = CaseStatus.CLOSED; db.commit(); db.close()
    err(route(client, org, specialty="COLPOSCOPY"), 409, "CASE_CLOSED")

def test_specialty_can_come_from_the_case(client, org, spec):
    db = client.session_factory(); db.get(Case, org["ids"]["ca"]).required_specialty = "COLPOSCOPY"; db.commit(); db.close()
    assert route(client, org).json()["data"]["routing"]["requiredSpecialty"] == "COLPOSCOPY"

def test_explicit_clinician_and_custom_limits(client, org, spec):
    st = route(client, org, specialty="COLPOSCOPY", receivingClinicianId=org["ids"]["recvB"], firstLimitMinutes=5, secondLimitMinutes=10).json()["data"]["routing"]
    assert st["routedClinician"]["id"] == org["ids"]["recvB"] and st["firstLimitMinutes"] == 5 and st["secondLimitMinutes"] == 10
    # a clinician from another facility can then see and accept it, without any worklist access
    assert mine(client, org, "recvB").json()["data"][0]["caseId"] == "CA"
    assert client.get(f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("recvB")).status_code == 200
    assert client.get("/api/worklist", headers=org["auth"]("recvB")).status_code == 403
    assert client.get(f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("recvC")).status_code == 404

# ---------- acceptance ----------

def test_accept(client, org, spec):
    route(client, org, specialty="COLPOSCOPY")
    err(accept(client, org, "recvB"), 404)                     # not routed to them
    err(accept(client, org, "coord"), 403)
    d = accept(client, org, "recv").json()["data"]
    assert d["routingStatus"] == "ACCEPTED" and d["routing"]["acceptedAt"] and d["routingDueAt"] is None
    ev = events(client, org)[-1]
    assert ev["eventType"] == "URGENT_CASE_ACCEPTED" and ev["actorRole"] == "RECEIVING_CLINICIAN" and ev["actorId"] == org["ids"]["recv"]
    err(accept(client, org, "recv"), 409, "INVALID_ROUTING_STATE")
    assert mine(client, org, "recv", "?status=ACCEPTED").json()["meta"]["total"] == 1 and mine(client, org, "recv", "?status=AWAITING_ACCEPTANCE").json()["meta"]["total"] == 0
    assert client.get("/api/dashboard/summary", headers=org["auth"]("recv")).json()["data"]["urgentRouting"] == {"awaitingAcceptance": 0, "accepted": 1}
    err(mine(client, org, "recv", "?status=BOGUS"), 422, "VALIDATION_ERROR")

def test_accept_validates_specialty_and_logs_the_refusal(client, org, spec):
    route(client, org, specialty="COLPOSCOPY")
    db = client.session_factory(); db.get(User, org["ids"]["recv"]).specialty = "SURGERY"; db.commit(); db.close()
    err(accept(client, org, "recv"), 403, "SPECIALTY_MISMATCH")
    assert state(client, org)["status"] == "AWAITING_ACCEPTANCE"        # unchanged
    assert types(client, org)[-1] == "INVALID_ACTION_REJECTED"

# ---------- exception, reassignment ----------

def test_no_qualified_clinician_is_an_exception_that_staff_can_resolve(client, org, spec):
    st = route(client, org, specialty="NEUROSURGERY").json()["data"]["routing"]
    assert st["status"] == "EXCEPTION" and st["routedClinician"] is None and "NEUROSURGERY" in st["exceptionReason"]
    assert len(open_tasks(client, org, "URGENT_ROUTING_EXCEPTION")) == 1
    assert types(client, org)[-1] == "URGENT_ROUTING_EXCEPTION"
    stats = client.get("/api/dashboard/summary", headers=org["auth"]("coord")).json()["data"]["stats"]
    assert stats["urgentRoutingExceptions"] == 1
    ids = org["ids"]
    def reassign(who, **body): return client.post(f"/api/cases/{ids['ca']}/urgent-routing/reassign", headers=org["auth"](who), json=body)
    err(reassign("coord", receivingClinicianId=ids["recvB"]), 422, "VALIDATION_ERROR")                # reason required
    err(reassign("coord", receivingClinicianId=ids["recvB"], reason="x"), 422, "SPECIALTY_MISMATCH")    # recvB is a colposcopist, case needs NEUROSURGERY
    db = client.session_factory(); db.get(User, ids["recvB"]).specialty = "NEUROSURGERY"; db.commit(); db.close()
    err(reassign("recv", receivingClinicianId=ids["recvB"], reason="x"), 404)
    err(reassign("fadmin", receivingClinicianId=ids["recvB"], reason="x"), 403)
    st = reassign("coord", receivingClinicianId=ids["recvB"], reason="Found a neurosurgeon").json()["data"]["routing"]
    assert st["status"] == "AWAITING_ACCEPTANCE" and st["stage"] == 0 and st["routedClinician"]["id"] == ids["recvB"] and st["exceptionReason"] is None
    assert open_tasks(client, org, "URGENT_ROUTING_EXCEPTION") == []                                    # alert closed
    ev = events(client, org)[-1]
    assert ev["eventType"] == "URGENT_ROUTING_REASSIGNED" and ev["actorRole"] == "COORDINATOR"
    assert accept(client, org, "recvB").status_code == 200
    err(reassign("coord", receivingClinicianId=ids["recvB"], reason="again"), 409, "INVALID_ROUTING_STATE")   # already accepted

def test_manual_reassignment_while_awaiting(client, org, spec):
    route(client, org, specialty="COLPOSCOPY")
    r = client.post(f"/api/cases/{org['ids']['ca']}/urgent-routing/reassign", headers=org["auth"]("coord"), json={"receivingClinicianId": org["ids"]["recvB"], "reason": "On leave"})
    assert r.json()["data"]["routing"]["routedClinician"]["id"] == org["ids"]["recvB"]
    err(accept(client, org, "recv"), 404)                                                              # the first clinician lost it
    assert accept(client, org, "recvB").status_code == 200

# ---------- time limits ----------

def test_limits_escalate_to_the_coordinator_then_a_backup_then_an_exception(client, org, spec):
    ids = org["ids"]
    route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=1, secondLimitMinutes=1)
    assert process(client, org).json()["data"] == {"processed": 0, "escalated": 0, "reassigned": 0, "exceptions": 0}   # not due yet
    make_due(client, org)
    assert process(client, org).json()["data"] == {"processed": 1, "escalated": 1, "reassigned": 0, "exceptions": 0}
    st = state(client, org)
    assert st["stage"] == 1 and st["escalatedToCoordinator"] is True and st["status"] == "AWAITING_ACCEPTANCE" and st["routedClinician"]["id"] == ids["recv"]
    assert datetime.fromisoformat(st["dueAt"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
    assert len(open_tasks(client, org, "URGENT_ROUTING_ESCALATED")) == 1
    assert process(client, org).json()["data"]["processed"] == 0                                        # idempotent until the next deadline
    make_due(client, org)
    assert process(client, org).json()["data"] == {"processed": 1, "escalated": 0, "reassigned": 1, "exceptions": 0}
    st = state(client, org)
    assert st["stage"] == 2 and st["routedClinician"]["id"] == ids["recvB"] and st["status"] == "AWAITING_ACCEPTANCE"
    err(accept(client, org, "recv"), 404)                                                               # the original clinician no longer holds it
    assert mine(client, org, "recvB").json()["data"][0]["caseId"] == "CA"
    make_due(client, org)
    assert process(client, org).json()["data"] == {"processed": 1, "escalated": 0, "reassigned": 0, "exceptions": 1}
    st = state(client, org)
    assert st["status"] == "EXCEPTION" and st["routedClinician"] is None and "backup clinician did not accept" in st["exceptionReason"]
    assert len(open_tasks(client, org, "URGENT_ROUTING_EXCEPTION")) == 1
    assert [t for t in types(client, org) if t.startswith("URGENT")] == ["URGENT_CASE_ROUTED", "URGENT_ROUTING_ESCALATED", "URGENT_ROUTING_REASSIGNED", "URGENT_ROUTING_EXCEPTION"]
    reassigned = next(e for e in events(client, org) if e["eventType"] == "URGENT_ROUTING_REASSIGNED")
    assert reassigned["actorRole"] == "COORDINATOR"

def test_backup_can_accept(client, org, spec):
    route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=1, secondLimitMinutes=1)
    for _ in range(2): make_due(client, org); process(client, org)
    assert state(client, org)["routedClinician"]["id"] == org["ids"]["recvB"]
    assert accept(client, org, "recvB").json()["data"]["routingStatus"] == "ACCEPTED"
    make_due(client, org); assert process(client, org).json()["data"]["processed"] == 0                 # accepted cases never escalate

def test_primary_can_still_accept_after_escalation_and_the_alert_closes(client, org, spec):
    route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=1)
    make_due(client, org); process(client, org)
    assert len(open_tasks(client, org, "URGENT_ROUTING_ESCALATED")) == 1
    assert accept(client, org, "recv").status_code == 200
    assert open_tasks(client, org, "URGENT_ROUTING_ESCALATED") == []

def test_no_backup_available_is_an_exception(client, org, spec):
    db = client.session_factory(); db.get(User, org["ids"]["recvB"]).specialty = "SURGERY"; db.commit(); db.close()
    route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=1, secondLimitMinutes=1)
    for _ in range(2): make_due(client, org); process(client, org)
    st = state(client, org)
    assert st["status"] == "EXCEPTION" and "no qualified backup clinician" in st["exceptionReason"]

def test_inactive_clinicians_are_not_chosen_as_backup(client, org, spec):
    db = client.session_factory(); db.get(User, org["ids"]["recvB"]).is_active = False; db.commit(); db.close()
    route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=1, secondLimitMinutes=1)
    for _ in range(2): make_due(client, org); process(client, org)
    assert state(client, org)["status"] == "EXCEPTION"

def test_process_due_is_role_and_scope_limited(client, org, spec):
    route(client, org, specialty="COLPOSCOPY", firstLimitMinutes=1); make_due(client, org)
    for who in ("refer", "recv", "fadmin", "ai"): err(process(client, org, who), 403)
    assert process(client, org, "coordB").json()["data"]["processed"] == 0           # facility B cannot touch facility A's case
    assert process(client, org, "national").json()["data"]["processed"] == 1

# ---------- contract ----------

def test_worklist_exposes_routing_and_flat_aliases(client, org, spec):
    route(client, org, specialty="COLPOSCOPY")
    row = next(c for c in client.get("/api/worklist", headers=org["auth"]("coord")).json()["data"]["cases"] if c["caseId"] == "CA")
    assert row["routingStatus"] == "AWAITING_ACCEPTANCE" and row["specialty"] == "COLPOSCOPY" and row["routing"]["routedClinician"]["id"] == org["ids"]["recv"]
    assert row["patientLabel"] == "PA" and row["patient"]["displayLabel"] == "PA" and "age" in row and "sex" in row and "screeningType" in row and "assignedTo" in row
    f = lambda q: client.get(f"/api/worklist{q}", headers=org["auth"]("coord")).json()["data"]["total"]
    assert f("?routingStatus=AWAITING_ACCEPTANCE") == 1 and f("?routingStatus=EXCEPTION") == 0
    err(client.get("/api/worklist?routingStatus=BOGUS", headers=org["auth"]("coord")), 422, "VALIDATION_ERROR")
    assert client.get("/api/dashboard/summary", headers=org["auth"]("coord")).json()["data"]["stats"]["awaitingUrgentAcceptance"] == 1
    assert client.get("/api/dashboard/summary", headers=org["auth"]("recv")).json()["data"]["urgentRouting"] == {"awaitingAcceptance": 1, "accepted": 0}

def test_case_create_can_carry_the_required_specialty(client, org):
    ids = org["ids"]
    r = client.post("/api/cases", headers=org["auth"]("coord"), json={"patientId": ids["pa"], "caseId": "NEW-9", "facilityId": ids["fa"], "priority": "URGENT", "requiredSpecialty": "colposcopy"})
    assert r.status_code == 200
    row = next(c for c in client.get("/api/worklist", headers=org["auth"]("coord")).json()["data"]["cases"] if c["caseId"] == "NEW-9")
    assert row["specialty"] == "COLPOSCOPY"

def test_referral_response_has_referring_clinician_details(client, org):
    db = client.session_factory(); db.get(Case, org["ids"]["ca"]).delay_reason_code = "AWAITING_RESULTS"; db.commit(); db.close()
    # T9 requires the result to be acknowledged and understood before referral.
    ack = client.post(
        f"/api/cases/{org['ids']['ca']}/assisted-responses",
        headers=org["auth"]("coord"),
        json={"acknowledged": True, "understood": "YES", "confidence": 4,
              "explanationStatus": "EXPLAINED", "callbackRequested": False},
    )
    assert ack.status_code == 200, ack.text
    d = client.post("/api/referrals", headers=org["auth"]("refer"), json={"caseId": org["ids"]["ca"], "receivingFacilityId": org["ids"]["fb"]}).json()["data"]
    assert d["referredBy"] == {"id": org["ids"]["refer"], "displayName": "Demo Referring Clinician", "role": "REFERRING_CLINICIAN"}
