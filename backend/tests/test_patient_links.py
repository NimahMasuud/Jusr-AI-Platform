from datetime import datetime, timedelta, timezone
import pytest
from app.models.entities import Case, CaseStatus, Patient, PatientLink

def err(r, status, code=None):
    assert r.status_code == status, r.text
    assert r.json()["success"] is False
    if code: assert r.json()["error"]["code"] == code

def gen(client, org, who="coord", case="ca"):
    return client.post(f"/api/cases/{org['ids'][case]}/links", headers=org["auth"](who))

def token(client, org, **kw):
    r = gen(client, org, **kw); assert r.status_code == 200, r.text
    return r.json()["data"]["token"]

def set_birth_year(client, org, year=1990):
    db = client.session_factory(); db.get(Patient, org["ids"]["pa"]).birth_year = year; db.commit(); db.close()

def tasks(client, org, who="coord", q=""):
    return client.get(f"/api/tasks{q}", headers=org["auth"](who)).json()["data"]

def test_generate_link_is_random_unlinked_to_personal_info_and_stored_hashed(client, org):
    d = gen(client, org).json()["data"]
    assert d["url"].endswith("/p/" + d["token"]) and len(d["token"]) >= 40
    for secret in (org["ids"]["ca"], org["ids"]["pa"], "CA", "PA"):
        assert secret not in d["url"]
    assert d["token"] != token(client, org)                      # random each time
    db = client.session_factory()
    assert all(l.token_hash != d["token"] and len(l.token_hash) == 64 for l in db.query(PatientLink).all()); db.close()
    exp = datetime.fromisoformat(d["expiresAt"].replace("Z", "+00:00"))
    assert timedelta(days=6, hours=23) < exp - datetime.now(timezone.utc) <= timedelta(days=7, minutes=1)

@pytest.mark.parametrize("who,status", [("fadmin", 403), ("patient", 403), ("ai", 403), ("recv", 404), ("coordB", 404)])
def test_generate_permissions(client, org, who, status):
    err(gen(client, org, who), status)

def test_closed_case_gets_no_link(client, org):
    db = client.session_factory(); db.get(Case, org["ids"]["ca"]).status = CaseStatus.CLOSED; db.commit(); db.close()
    err(gen(client, org), 409, "CASE_CLOSED")

def test_resend_cancels_previous_link(client, org):
    t1 = token(client, org)
    assert client.get(f"/p/{t1}").status_code == 200
    r2 = gen(client, org); t2 = r2.json()["data"]["token"]
    assert r2.json()["data"]["resent"] is True
    err(client.get(f"/p/{t1}"), 410, "LINK_SUPERSEDED")
    assert client.get(f"/p/{t2}").status_code == 200
    statuses = [l["status"] for l in client.get(f"/api/cases/{org['ids']['ca']}/links", headers=org["auth"]("coord")).json()["data"]]
    assert sorted(statuses) == ["ACTIVE", "SUPERSEDED"]
    assert "token" not in str(client.get(f"/api/cases/{org['ids']['ca']}/links", headers=org["auth"]("coord")).json())

def test_unknown_and_expired_tokens(client, org):
    err(client.get("/p/not-a-real-token"), 404, "LINK_NOT_FOUND")
    err(client.post("/p/not-a-real-token/ack"), 404, "LINK_NOT_FOUND")
    t = token(client, org)
    db = client.session_factory(); db.query(PatientLink).one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit(); db.close()
    err(client.get(f"/p/{t}"), 410, "LINK_EXPIRED")
    err(client.post(f"/p/{t}/ack"), 410, "LINK_EXPIRED")
    statuses = [l["status"] for l in client.get(f"/api/cases/{org['ids']['ca']}/links", headers=org["auth"]("coord")).json()["data"]]
    assert statuses == ["EXPIRED"]

def test_patient_view_is_limited_to_what_the_patient_needs(client, org):
    d = client.get(f"/p/{token(client, org)}").json()["data"]
    assert set(d) == {"patient", "facility", "screening", "nextAction", "dueAt", "expiresAt", "responses",
                      "status", "priority", "urgencyText", "contact", "language", "reassuranceAvailable", "progress"}
    assert d["patient"] == {"displayLabel": "PA"} and d["facility"] == {"name": "A"}
    assert "CB" not in str(d) and "PB" not in str(d)

def test_no_verification_when_patient_has_no_birth_year(client, org):
    t = token(client, org)
    assert client.post(f"/p/{t}/ack").status_code == 200
    r = client.post(f"/p/{t}/verify", json={"birthYear": 1990}).json()["data"]
    assert r["verificationRequired"] is False and r["sessionToken"] is None

def test_birth_year_verification_gate(client, org):
    set_birth_year(client, org, 1990)
    t = token(client, org)
    r = client.get(f"/p/{t}"); err(r, 403, "VERIFICATION_REQUIRED")
    assert r.json()["error"]["details"] == {"verificationRequired": True, "attemptsRemaining": 3}
    err(client.post(f"/p/{t}/ack"), 403, "VERIFICATION_REQUIRED")
    err(client.post(f"/p/{t}/verify", json={"birthYear": 1991}), 403, "VERIFICATION_FAILED")
    assert client.post(f"/p/{t}/verify", json={"birthYear": 1991}).json()["error"]["details"]["attemptsRemaining"] == 1
    err(client.post(f"/p/{t}/verify", json={}), 422, "VALIDATION_ERROR")
    ok = client.post(f"/p/{t}/verify", json={"birthYear": 1990}); assert ok.status_code == 200
    h = {"X-Patient-Session": ok.json()["data"]["sessionToken"]}
    assert client.get(f"/p/{t}", headers=h).status_code == 200
    assert client.post(f"/p/{t}/ack", headers=h).status_code == 200
    # a session only works for the link it was issued for, and a staff token is not a patient session
    other = token(client, org)
    err(client.post(f"/p/{other}/ack", headers=h), 403, "VERIFICATION_REQUIRED")
    staff = org["auth"]("coord")["Authorization"].split()[1]
    err(client.post(f"/p/{other}/ack", headers={"X-Patient-Session": staff}), 403, "VERIFICATION_REQUIRED")

def test_three_wrong_attempts_lock_the_link_and_create_a_coordinator_task(client, org):
    set_birth_year(client, org, 1990)
    t = token(client, org)
    for _ in range(2): err(client.post(f"/p/{t}/verify", json={"birthYear": 2000}), 403, "VERIFICATION_FAILED")
    err(client.post(f"/p/{t}/verify", json={"birthYear": 2000}), 423, "LINK_LOCKED")
    err(client.post(f"/p/{t}/verify", json={"birthYear": 1990}), 423, "LINK_LOCKED")   # correct year no longer helps
    err(client.get(f"/p/{t}"), 423, "LINK_LOCKED")
    open_tasks = tasks(client, org, q="?type=LINK_LOCKED&status=OPEN")
    assert len(open_tasks) == 1 and open_tasks[0]["caseId"] == org["ids"]["ca"]
    types = [e["eventType"] for e in client.get(f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("coord")).json()["data"]]
    assert types.count("LINK_VERIFICATION_FAILED") == 2 and "LINK_LOCKED" in types
    # staff resend replaces the locked link
    t2 = token(client, org)
    err(client.get(f"/p/{t2}"), 403, "VERIFICATION_REQUIRED")
    assert client.post(f"/p/{t2}/verify", json={"birthYear": 1990}).status_code == 200

def test_patient_responses_and_tasks(client, org):
    t = token(client, org)
    assert client.post(f"/p/{t}/ack").status_code == 200
    assert client.post(f"/p/{t}/understanding", json={"understood": True}).status_code == 200
    for bad in (0, 6, "x"): err(client.post(f"/p/{t}/confidence", json={"rating": bad}), 422, "VALIDATION_ERROR")
    err(client.post(f"/p/{t}/understanding", json={}), 422, "VALIDATION_ERROR")
    assert client.post(f"/p/{t}/confidence", json={"rating": 4}).status_code == 200
    assert client.post(f"/p/{t}/not-explained").status_code == 200
    assert client.post(f"/p/{t}/callback", json={"preferredTime": "mornings"}).status_code == 200
    assert client.post(f"/p/{t}/callback").status_code == 200                     # no duplicate task for the same link
    r = client.get(f"/p/{t}").json()["data"]["responses"]
    assert r == {"acknowledged": True, "understood": True, "confidence": 4, "explanationStatus": "NOT_EXPLAINED", "callbackRequested": True}
    assert sorted(x["type"] for x in tasks(client, org, q="?status=OPEN")) == ["CALLBACK_REQUESTED", "NOT_EXPLAINED"]
    rows = client.get(f"/api/cases/{org['ids']['ca']}/patient-responses", headers=org["auth"]("coord")).json()["data"]
    assert {x["source"] for x in rows} == {"PATIENT_LINK"} and all(x["recordedBy"] is None for x in rows)
    ev = [e for e in client.get(f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("coord")).json()["data"] if e["eventType"] == "PATIENT_RESPONSE"]
    assert len(ev) == 6 and all(e["actorRole"] == "PATIENT" and e["actorId"] is None for e in ev)

def test_task_listing_and_completion(client, org):
    t = token(client, org); client.post(f"/p/{t}/callback")
    task = tasks(client, org)[0]
    assert tasks(client, org, "coordB") == [] and client.get("/api/tasks", headers=org["auth"]("fadmin")).status_code == 403
    err(client.post(f"/api/tasks/{task['id']}/complete", headers=org["auth"]("recv")), 403)
    assert client.post(f"/api/tasks/{task['id']}/complete", headers=org["auth"]("coord")).json()["data"]["status"] == "DONE"
    err(client.post(f"/api/tasks/{task['id']}/complete", headers=org["auth"]("coord")), 409, "TASK_ALREADY_DONE")
    err(client.get("/api/tasks?status=NOPE", headers=org["auth"]("coord")), 422, "VALIDATION_ERROR")

BODY = {"acknowledged": True, "understood": False, "confidence": 2, "explanationStatus": "NOT_EXPLAINED", "callbackRequested": True, "note": "Phoned at clinic"}

def assisted(client, org, who="coord", body=None, case="ca"):
    return client.post(f"/api/cases/{org['ids'][case]}/assisted-responses", headers=org["auth"](who), json=BODY if body is None else body)

def test_assisted_response_is_attributed_to_staff_not_the_patient(client, org):
    r = assisted(client, org); assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["source"] == "STAFF_ASSISTED" and d["submittedByPatient"] is False
    assert d["recordedBy"]["id"] == org["ids"]["coord"] and d["recordedBy"]["role"] == "COORDINATOR" and d["recordedAt"]
    assert {x["source"] for x in d["responses"]} == {"STAFF_ASSISTED"}
    assert all(x["recordedBy"]["role"] == "COORDINATOR" for x in d["responses"])
    assert sorted(x["type"] for x in tasks(client, org, q="?status=OPEN")) == ["CALLBACK_REQUESTED", "NOT_EXPLAINED"]
    ev = [e for e in client.get(f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("coord")).json()["data"] if e["eventType"] == "ASSISTED_RESPONSE_RECORDED"]
    assert len(ev) == 1 and ev[0]["actorRole"] == "COORDINATOR" and ev[0]["actorId"] == org["ids"]["coord"]

def test_assisted_response_requires_every_field(client, org):
    for missing in ("acknowledged", "understood", "confidence", "explanationStatus", "callbackRequested"):
        err(assisted(client, org, body={k: v for k, v in BODY.items() if k != missing}), 422, "VALIDATION_ERROR")
    err(assisted(client, org, body={**BODY, "confidence": 0}), 422, "VALIDATION_ERROR")
    err(assisted(client, org, body={**BODY, "explanationStatus": "MAYBE"}), 422, "VALIDATION_ERROR")
    ok = assisted(client, org, body={**BODY, "understood": True, "explanationStatus": "EXPLAINED", "callbackRequested": False, "note": None})
    assert ok.status_code == 200 and tasks(client, org, q="?status=OPEN") == []

@pytest.mark.parametrize("who,status", [("fadmin", 403), ("patient", 403), ("ai", 403), ("recv", 404), ("coordB", 404)])
def test_assisted_permissions(client, org, who, status):
    err(assisted(client, org, who), status)

def test_staff_can_read_mixed_responses_with_clear_sources(client, org):
    t = token(client, org); client.post(f"/p/{t}/ack"); assisted(client, org, who="refer")
    rows = client.get(f"/api/cases/{org['ids']['ca']}/patient-responses", headers=org["auth"]("coord")).json()["data"]
    assert {x["source"] for x in rows} == {"PATIENT_LINK", "STAFF_ASSISTED"}
    assert {x["recordedBy"]["role"] for x in rows if x["source"] == "STAFF_ASSISTED"} == {"REFERRING_CLINICIAN"}
    err(client.get(f"/api/cases/{org['ids']['ca']}/patient-responses", headers=org["auth"]("fadmin")), 403)
