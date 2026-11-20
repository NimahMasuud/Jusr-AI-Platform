import pytest
from app.models.entities import Case
from app.models.entities import Case, User

def test_api_alias_serves_same_routes(client, org):
    h = org["auth"]("coord")
    assert client.get("/api/worklist", headers=h).status_code == 200
    assert client.get("/api/v1/worklist", headers=h).status_code == 200
    assert client.get("/api/dashboard/summary", headers=h).status_code == 200
    assert "/api/worklist" not in client.get("/api/v1/openapi.json").json()["paths"]

@pytest.mark.parametrize("who", ["fadmin", "patient"])
@pytest.mark.parametrize("path", ["/api/cases", "/api/worklist", "/api/patients", "/api/cases/{ca}/events", "/api/patients/{pa}"])
def test_non_clinical_roles_cannot_read_clinical_data(client, org, who, path):
    r = client.get(path.format(**org["ids"]), headers=org["auth"](who))
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"

def test_facility_admin_dashboard_has_no_case_data(client, org):
    r = client.get("/api/dashboard/summary", headers=org["auth"]("fadmin"))
    data = r.json()["data"]
    assert r.status_code == 200 and data["role"] == "FACILITY_ADMIN"
    assert set(data) == {"role", "generatedAt", "facility", "staffAccess", "connection"}
    assert data["staffAccess"]["totalStaff"] == 5  # facility A staff only, no patient accounts
    assert not any(k in data for k in ("stats", "referrals", "cases"))

def test_patient_role_has_no_dashboard(client, org):
    assert client.get("/api/dashboard/summary", headers=org["auth"]("patient")).status_code == 403

def test_dashboard_role_shapes(client, org):
    h = org["auth"]
    c = client.get("/api/dashboard/summary", headers=h("coord")).json()["data"]
    assert c["stats"]["activeCases"] == 1 and c["stats"]["overdueCases"] == 1 and c["stats"]["urgentCases"] == 1
    assert "assignedCases" in client.get("/api/dashboard/summary", headers=h("refer")).json()["data"]["stats"]
    r = client.get("/api/dashboard/summary", headers=h("recv")).json()["data"]
    assert r["referrals"] == {"incoming": 1, "pending": 1, "accepted": 0, "urgent": 0, "assignedToMe": 0, "outstandingDecisions": 1}

def test_role_is_taken_from_session_not_query(client, org):
    r = client.get("/api/dashboard/summary?role=COORDINATOR&facilityId=x", headers=org["auth"]("fadmin"))
    assert r.json()["data"]["role"] == "FACILITY_ADMIN" and "stats" not in r.json()["data"]

def test_facility_scoping_and_cross_facility_owner(client, org):
    h, ids = org["auth"], org["ids"]
    rows = lambda who: {c["caseId"] for c in client.get("/api/worklist", headers=h(who)).json()["data"]["cases"]}
    assert rows("coord") == {"CA"} and rows("coordB") == {"CB"} and rows("national") == {"CA", "CB"}
    # receiving clinicians are off the general worklist and case list; they only reach cases referred or routed to them
    for path in ("/api/worklist", "/api/cases"):
        assert client.get(path, headers=h("recv")).status_code == 403
    assert client.get(f"/api/cases/{ids['cb']}/events", headers=h("recv")).status_code == 200   # CB was referred into facility A
    assert client.get(f"/api/cases/{ids['ca']}/events", headers=h("recv")).status_code == 404   # CA is just another case at their facility
    assert client.get(f"/api/cases/{ids['cb']}/events", headers=h("coord")).status_code == 404
    # named owner from another facility gains access
    db = client.session_factory(); db.get(Case, ids["cb"]).coordinator_id = ids["coord"]; db.commit(); db.close()
    assert rows("coord") == {"CA", "CB"}
    assert client.get(f"/api/cases/{ids['cb']}/events", headers=h("coord")).status_code == 200

def test_patients_scoped_to_facility(client, org):
    h, ids = org["auth"], org["ids"]

    response = client.get("/api/patients?page=1&pageSize=200", headers=h("coord"))
    assert response.status_code == 200

    got = {p["displayLabel"] for p in response.json()["data"]}

    assert "PA" in got
    assert "PB" not in got

    assert client.get(
        f"/api/patients/{ids['pb']}",
        headers=h("coord"),
    ).status_code == 404

    assert client.get(
        f"/api/patients/{ids['pb']}",
        headers=h("national"),
    ).status_code == 200

    r = client.post(
        "/api/patients",
        headers=h("coord"),
        json={"displayLabel": "New"},
    )
    assert r.status_code == 200

    assert client.get(
        f"/api/patients/{r.json()['data']['id']}",
        headers=h("coord"),
    ).status_code == 200

    assert client.get(
        f"/api/patients/{r.json()['data']['id']}",
        headers=h("coordB"),
    ).status_code == 404

def test_no_cross_facility_writes(client, org):
    h, ids = org["auth"], org["ids"]
    for who in ("coord", "fadmin", "refer"):
        r = client.post(f"/api/cases/{ids['cb']}/transition", headers=h(who), json={"status": "IN_PROGRESS"})
        assert r.status_code in (403, 404), (who, r.status_code)
    assert client.post(f"/api/cases/{ids['cb']}/assign", headers=h("coord"), json={"coordinatorId": ids["coord"]}).status_code == 404
    # receiving clinician can see the referred case but not change its workflow
    assert client.post(f"/api/cases/{ids['cb']}/transition", headers=h("recv"), json={"status": "IN_PROGRESS"}).status_code in (403, 404)

def test_ai_service_is_read_only(client, org):
    h, ids = org["auth"]("ai"), org["ids"]
    assert client.get("/api/worklist", headers=h).status_code == 200
    assert client.post(f"/api/cases/{ids['ca']}/transition", headers=h, json={"status": "IN_PROGRESS"}).status_code == 403
    assert client.post(f"/api/cases/{ids['ca']}/assign", headers=h, json={"coordinatorId": ids["coord"]}).status_code == 403
    assert client.post("/api/patients", headers=h, json={"displayLabel": "x"}).status_code == 403

def test_assignee_must_be_active_coordinator(client, org):
    h, ids = org["auth"]("coord"), org["ids"]

    # An inactive clinical staff member cannot be assigned.
    db = client.session_factory()
    referring = db.get(User, ids["refer"])
    referring.is_active = False
    db.commit()
    db.close()

    r = client.post(
        f"/api/cases/{ids['ca']}/assign",
        headers=h,
        json={"coordinatorId": ids["refer"]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_ASSIGNEE"

    # An active coordinator can be assigned.
    assert client.post(
        f"/api/cases/{ids['ca']}/assign",
        headers=h,
        json={"coordinatorId": ids["coord"]},
    ).status_code == 200

    # Facility administrators cannot perform clinical assignments.
    assert client.post(
        f"/api/cases/{ids['ca']}/assign",
        headers=org["auth"]("fadmin"),
        json={"coordinatorId": ids["coord"]},
    ).status_code == 403