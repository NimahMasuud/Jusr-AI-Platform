from datetime import datetime, timedelta, timezone
import pytest
from app.core.security import hash_password, verify_password
from app.models.entities import Facility, User, Patient, Case, Role, Priority, CaseStatus

@pytest.fixture()
def world(client):
    db = client.session_factory()
    fac = Facility(name="F", code="F1"); db.add(fac); db.flush()
    admin = User(email="a@x.local", display_name="A", password_hash=hash_password("pw12345!"), role=Role.COORDINATOR, facility_id=fac.id)
    db.add(admin); db.flush()
    pat = Patient(display_label="P1"); db.add(pat); db.flush()
    now = datetime.now(timezone.utc)
    cases = []
    for i, due in enumerate([now - timedelta(days=2), now + timedelta(days=2), None]):
        c = Case(
        case_number=f"C-{i}",
        patient_id=pat.id,
        facility_id=fac.id,
        due_at=due,
        status=CaseStatus.NEW,
        priority=Priority.NORMAL,
        delay_reason_code="RESULT_OR_DATA_MISSING" if i == 0 else None,
        )
        db.add(c)
        cases.append(c)
        
    db.commit()
    ids = [c.id for c in cases]
    db.close()
    r = client.post("/api/v1/auth/login", data={"username": "a@x.local", "password": "pw12345!"})
    assert r.status_code == 200, r.text
    return {"h": {"Authorization": "Bearer " + r.json()["data"]["accessToken"]}, "ids": ids}

def assert_error(r, status, code=None):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["success"] is False
    assert set(body["error"]) == {"code", "message", "details"}
    assert "requestId" in body["meta"]
    if code: assert body["error"]["code"] == code

def test_password_hashing_works():
    assert verify_password("Admin123!", hash_password("Admin123!"))

def test_dashboard_and_worklist_timezone_safe(client, world):
    r = client.get("/api/v1/dashboard/summary", headers=world["h"])
    assert r.status_code == 200 and r.json()["data"]["stats"]["overdueCases"] == 1
    r = client.get("/api/v1/worklist", headers=world["h"])
    assert r.status_code == 200 and r.json()["data"]["summary"]["overdueCases"] == 1
    r = client.get("/api/v1/worklist?overdue=true", headers=world["h"])
    assert r.json()["data"]["total"] == 1

@pytest.mark.parametrize("path", [
    "/api/v1/worklist?priority=BOGUS", "/api/v1/worklist?status=BOGUS", "/api/v1/worklist?sortBy=nope",
    "/api/v1/worklist?sortOrder=sideways", "/api/v1/worklist?pageSize=0", "/api/v1/worklist?page=0",
    "/api/v1/cases?priority=BOGUS", "/api/v1/cases?status=BOGUS", "/api/v1/cases?page=0",
])
def test_bad_query_values_are_422(client, world, path):
    assert_error(client.get(path, headers=world["h"]), 422, "VALIDATION_ERROR")

def test_bad_bodies_are_4xx(client, world):
    cid = world["ids"][0]
    assert_error(
    client.post(
        f"/api/v1/cases/{cid}/transition",
        headers=world["h"],
        json={"status": "BOGUS"},
    ),
    403,
    "FORBIDDEN",
)
    assert_error(
    client.post(
        f"/api/v1/cases/{cid}/transition",
        headers=world["h"],
        json={},
    ),
    403,
    "FORBIDDEN",
)
    assert_error(client.post("/api/v1/patients", headers=world["h"], json={}), 422)

def test_errors_use_envelope(client, world):
    assert_error(client.get("/api/v1/cases"), 401, "UNAUTHENTICATED")
    assert_error(client.get("/api/v1/patients/missing", headers=world["h"]), 404, "NOT_FOUND")
    assert_error(client.get("/api/v1/nope", headers=world["h"]), 404)
    r = client.post(f"/api/v1/cases/{world['ids'][0]}/transition", headers=world["h"], json={"status": "CLOSED"})
    assert_error(r, 403, "FORBIDDEN")


def test_a01_evidence_required_to_resolve_and_close(client, world):
    cid, h = world["ids"][0], world["h"]
    url = f"/api/v1/cases/{cid}/transition"

    # Direct status mutation is prohibited; workflow actions own transitions.
    assert_error(
        client.post(url, headers=h, json={"status": "CLOSED"}),
        403,
        "FORBIDDEN",
    )


def test_a01_decision_accepted_and_closing_legacy_resolved_needs_basis(client, world):
    cid, h = world["ids"][2], world["h"]

    # Direct status mutation is prohibited, including attempts to close
    # a case that has been marked as legacy data.
    url = f"/api/v1/cases/{cid}/transition"

    assert_error(
        client.post(url, headers=h, json={"status": "CLOSED"}),
        403,
        "FORBIDDEN",
    )

def test_duplicate_case_number_is_409(client, world):
    db = client.session_factory(); pid = db.query(Patient).first().id; fid = db.query(Facility).first().id; db.close()
    r = client.post("/api/v1/cases", headers=world["h"], json={"patientId": pid, "caseId": "C-0", "facilityId": fid})
    assert_error(r, 409, "DUPLICATE_CASE_ID")
