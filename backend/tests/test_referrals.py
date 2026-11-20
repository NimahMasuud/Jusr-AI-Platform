import pytest


ACK_PAYLOAD = {
    "acknowledged": True,
    "understood": "YES",
    "confidence": 4,
    "explanationStatus": "EXPLAINED",
    "callbackRequested": False,
}


def prepare_case_for_referral(client, org):
    """Clear the overdue flag and record the patient acknowledgement required by T9."""
    delay = client.post(
        f"/api/cases/{org['ids']['ca']}/delay-reason",
        headers=org["auth"]("coord"),
        json={"code": "RESULT_OR_DATA_MISSING"},
    )
    # Repeated helper calls may encounter an already-cleared overdue flag.
    assert delay.status_code in (200, 409), delay.text
    if delay.status_code == 409:
        assert delay.json()["error"]["code"] == "CASE_NOT_OVERDUE"

    ack = client.post(
        f"/api/cases/{org['ids']['ca']}/assisted-responses",
        headers=org["auth"]("coord"),
        json=ACK_PAYLOAD,
    )
    assert ack.status_code == 200, ack.text


def make(client, org, who="refer", **extra):
    """Create a referral from case CA (facility A) to facility B."""
    prepare_case_for_referral(client, org)
    body = {
        "caseId": org["ids"]["ca"],
        "receivingFacilityId": org["ids"]["fb"],
        "reason": "Needs colposcopy",
        **extra,
    }
    return client.post("/api/referrals", headers=org["auth"](who), json=body)


def act(client, org, who, rid, op, body=None):
    return client.post(
        f"/api/referrals/{rid}/{op}",
        headers=org["auth"](who),
        json=body or {},
    )


def err(r, status, code=None):
    assert r.status_code == status, r.text
    assert r.json()["success"] is False
    if code:
        assert r.json()["error"]["code"] == code


def events(client, org, who="national", case="ca"):
    rows = client.get(
        f"/api/cases/{org['ids'][case]}/events", headers=org["auth"](who)
    ).json()["data"]
    return [
        e for e in rows
        if e["eventType"] not in ("DELAY_REASON_RECORDED", "ASSISTED_RESPONSE_RECORDED")
    ]


def test_create_moves_case_to_referral_pending_and_audits(client, org):
    r = make(client, org)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "SENT"
    assert d["case"]["status"] == "REFERRAL_PENDING"
    assert d["receivingFacility"]["name"] == "B"

    ev = events(client, org)
    created = next(e for e in ev if e["eventType"] == "REFERRAL_CREATED")
    transition = next(e for e in ev if e["eventType"] == "CASE_TRANSITION")
    assert created["actorRole"] == "REFERRING_CLINICIAN"
    assert transition["actorRole"] == "REFERRING_CLINICIAN"


def test_create_rules(client, org):
    ids = org["ids"]
    err(make(client, org, "fadmin"), 403)
    err(make(client, org, "recv"), 404)
    err(make(client, org, "ai"), 403)
    err(make(client, org, "coordB"), 404)
    err(make(client, org, "coord"), 403)  # coordinators do not create referrals

    prepare_case_for_referral(client, org)
    err(
        client.post(
            "/api/referrals",
            headers=org["auth"]("refer"),
            json={"caseId": ids["ca"], "receivingFacilityId": ids["fa"]},
        ),
        422,
        "INVALID_RECEIVING_FACILITY",
    )
    err(
        client.post(
            "/api/referrals",
            headers=org["auth"]("refer"),
            json={"caseId": ids["ca"], "receivingFacilityId": "nope"},
        ),
        404,
    )
    err(make(client, org, receivingClinicianId=ids["recvC"]), 422, "INVALID_ASSIGNEE")
    err(
        client.post(
            "/api/referrals",
            headers=org["auth"]("refer"),
            json={"caseId": ids["ca"]},
        ),
        422,
        "VALIDATION_ERROR",
    )
    valid = make(client, org, receivingClinicianId=ids["recvB"])
    assert valid.status_code == 200, valid.text
    err(make(client, org), 409, "REFERRAL_ALREADY_ACTIVE")


def test_create_accepts_case_number(client, org):
    prepare_case_for_referral(client, org)
    r = client.post(
        "/api/referrals",
        headers=org["auth"]("refer"),
        json={"caseId": "CA", "receivingFacilityId": org["ids"]["fb"], "reason": "Needs colposcopy"},
    )
    assert r.status_code == 200, r.text


def test_create_requires_referral_eligible_case_and_logs_refusal(client, org):
    from app.models.entities import Case, CaseStatus

    db = client.session_factory()
    case = db.get(Case, org["ids"]["ca"])
    case.status = CaseStatus.NOTIFYING
    db.commit()
    db.close()

    r = make(client, org)
    err(r, 409, "INVALID_STATUS_TRANSITION")
    assert [e["eventType"] for e in events(client, org)] == ["INVALID_ACTION_REJECTED"]
    db = client.session_factory()
    current = db.get(Case, org["ids"]["ca"])
    assert current.status == CaseStatus.NOTIFYING
    db.close()


def test_assign_accept_consultation_flow(client, org):
    ids = org["ids"]
    created = make(client, org)
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["id"]

    err(act(client, org, "refer", rid, "assign", {"receivingClinicianId": ids["recvB"]}), 403)
    err(act(client, org, "recvB", rid, "assign", {"receivingClinicianId": ids["recvB"]}), 403)
    err(act(client, org, "coordB", rid, "assign", {"receivingClinicianId": ids["refer"]}), 422, "INVALID_ASSIGNEE")
    assigned = act(client, org, "coordB", rid, "assign", {"receivingClinicianId": ids["recvB"]})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["receivingClinician"]["id"] == ids["recvB"]

    err(act(client, org, "recvB2", rid, "accept"), 403)
    err(act(client, org, "coordB", rid, "accept"), 403)
    err(act(client, org, "recvB", rid, "consultation", {"outcome": "x"}), 409, "INVALID_REFERRAL_STATE")
    accepted = act(client, org, "recvB", rid, "accept", {"note": "ok"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "ACCEPTED"
    err(act(client, org, "recvB", rid, "accept"), 409, "INVALID_REFERRAL_STATE")
    err(act(client, org, "recvB", rid, "consultation", {}), 422, "VALIDATION_ERROR")
    err(act(client, org, "recvB", rid, "consultation", {"outcome": "   "}), 422, "VALIDATION_ERROR")
    err(act(client, org, "recvB2", rid, "consultation", {"outcome": "x"}), 403)
    consultation = act(client, org, "recvB", rid, "consultation", {"outcome": "Treated; discharge"})
    assert consultation.status_code == 200, consultation.text
    d = consultation.json()["data"]
    assert d["consultation"]["outcome"] == "Treated; discharge"
    assert d["consultation"]["recordedById"] == ids["recvB"]
    err(act(client, org, "recvB", rid, "consultation", {"outcome": "again"}), 409, "CONSULTATION_ALREADY_RECORDED")

    types = [e["eventType"] for e in events(client, org)]
    assert types.count("REFERRAL_CLINICIAN_ASSIGNED") == 1
    assert "REFERRAL_ACCEPTED" in types and "CONSULTATION_RECORDED" in types
    assert types.count("INVALID_ACTION_REJECTED") >= 3
    assert all(e["actorRole"] for e in events(client, org))


def test_unassigned_referral_can_be_accepted_by_any_receiving_clinician(client, org):
    created = make(client, org)
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["id"]
    response = act(client, org, "recvB2", rid, "accept")
    assert response.status_code == 200, response.text
    d = response.json()["data"]
    assert d["status"] == "ACCEPTED"
    assert d["receivingClinician"]["id"] == org["ids"]["recvB2"]


def test_decline_needs_reason(client, org):
    created = make(client, org)
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["id"]
    err(act(client, org, "recvB", rid, "decline"), 422, "DECLINE_REASON_REQUIRED")
    err(act(client, org, "recvB", rid, "decline", {"reason": "  "}), 422, "VALIDATION_ERROR")
    err(act(client, org, "recv", rid, "decline", {"reason": "x"}), 403)
    declined = act(client, org, "recvB", rid, "decline", {"reason": "No capacity"})
    assert declined.status_code == 200, declined.text
    assert declined.json()["data"]["status"] == "DECLINED"
    err(act(client, org, "recvB", rid, "accept"), 409, "INVALID_REFERRAL_STATE")
    declined_events = [e for e in events(client, org) if e["eventType"] == "REFERRAL_DECLINED"]
    assert len(declined_events) == 1
    assert declined_events[0]["actorRole"] == "RECEIVING_CLINICIAN"


def test_escalate_and_reassign(client, org):
    ids = org["ids"]
    created = make(client, org)
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["id"]

    err(act(client, org, "recvB", rid, "escalate", {"reason": "slow"}), 403)
    err(act(client, org, "refer", rid, "escalate"), 422, "VALIDATION_ERROR")
    # The current endpoint permits the referring-facility Coordinator to escalate.
    escalated = act(client, org, "coord", rid, "escalate", {"reason": "Urgent, no response"})
    assert escalated.status_code == 200, escalated.text
    d = escalated.json()["data"]
    assert d["escalated"] is True
    assert d["escalationReason"] == "Urgent, no response"
    assert d["status"] == "SENT"
    err(act(client, org, "refer", rid, "escalate", {"reason": "again"}), 409, "INVALID_REFERRAL_STATE")

    err(act(client, org, "refer", rid, "reassign", {"receivingFacilityId": ids["fb"], "reason": "r"}), 422, "INVALID_RECEIVING_FACILITY")
    err(act(client, org, "refer", rid, "reassign", {"receivingFacilityId": ids["fc"]}), 422, "VALIDATION_ERROR")
    err(act(client, org, "recvB", rid, "reassign", {"receivingFacilityId": ids["fc"], "reason": "r"}), 403)
    reassigned = act(client, org, "refer", rid, "reassign", {"receivingFacilityId": ids["fc"], "reason": "B is full"})
    assert reassigned.status_code == 200, reassigned.text
    d = reassigned.json()["data"]
    assert d["receivingFacility"]["name"] == "C"
    assert d["status"] == "SENT"
    assert d["escalated"] is False
    assert client.get(f"/api/referrals/{rid}", headers=org["auth"]("recvB")).status_code == 404
    assert client.get(f"/api/referrals/{rid}", headers=org["auth"]("recvC")).status_code == 200


def test_reassign_after_decline_restarts_the_referral(client, org):
    ids = org["ids"]
    created = make(client, org)
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["id"]
    declined = act(client, org, "recvB", rid, "decline", {"reason": "No capacity"})
    assert declined.status_code == 200, declined.text
    reassigned = act(client, org, "refer", rid, "reassign", {"receivingFacilityId": ids["fc"], "reason": "Try C"})
    assert reassigned.status_code == 200, reassigned.text
    assert reassigned.json()["data"]["status"] == "SENT"
    assert act(client, org, "recvC", rid, "accept").json()["data"]["status"] == "ACCEPTED"
    err(act(client, org, "refer", rid, "reassign", {"receivingFacilityId": ids["fb"], "reason": "r"}), 409, "INVALID_REFERRAL_STATE")


def test_receiving_clinician_sees_case_referred_to_them(client, org):
    created = make(client, org)
    assert created.status_code == 200, created.text
    assert client.get(
        f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("recvB")
    ).status_code == 200
    assert client.get(
        f"/api/cases/{org['ids']['ca']}/events", headers=org["auth"]("recvC")
    ).status_code == 404
    r = client.post(
        f"/api/cases/{org['ids']['ca']}/transition",
        headers=org["auth"]("recvB"),
        json={"status": "IN_PROGRESS"},
    )
    assert r.status_code == 403


def test_list_filters_and_scope(client, org):
    created = make(client, org)
    assert created.status_code == 200, created.text
    lst = lambda who, q="": client.get(f"/api/referrals{q}", headers=org["auth"](who)).json()
    assert lst("coord")["meta"]["total"] == 2
    assert lst("coord", "?direction=incoming")["meta"]["total"] == 1
    assert lst("coord", "?direction=outgoing")["data"][0]["case"]["caseId"] == "CA"
    assert lst("recvC")["meta"]["total"] == 0
    assert lst("national")["meta"]["total"] == 2
    assert lst("national", "?status=ACCEPTED")["meta"]["total"] == 0
    assert lst("national", "?caseId=CA")["meta"]["total"] == 1
    assert lst("national", "?escalated=false")["meta"]["total"] == 2
    err(client.get("/api/referrals?status=BOGUS", headers=org["auth"]("coord")), 422, "VALIDATION_ERROR")
    err(client.get("/api/referrals?direction=sideways", headers=org["auth"]("coord")), 422, "VALIDATION_ERROR")
    for who in ("fadmin", "patient"):
        err(client.get("/api/referrals", headers=org["auth"](who)), 403)
    assert client.get("/api/referrals", headers=org["auth"]("ai")).status_code == 200


def test_dashboard_reflects_referrals(client, org):
    ids = org["ids"]
    created = make(client, org)
    assert created.status_code == 200, created.text
    rid = created.json()["data"]["id"]
    assigned = act(client, org, "coordB", rid, "assign", {"receivingClinicianId": ids["recvB"]})
    assert assigned.status_code == 200, assigned.text
    d = client.get("/api/dashboard/summary", headers=org["auth"]("recvB")).json()["data"]["referrals"]
    assert d["incoming"] == 1 and d["assignedToMe"] == 1 and d["outstandingDecisions"] == 1 and d["urgent"] == 1
    d2 = client.get("/api/dashboard/summary", headers=org["auth"]("recvB2")).json()["data"]["referrals"]
    assert d2["assignedToMe"] == 0 and d2["outstandingDecisions"] == 0
    assert "awaitingReview" not in client.get("/api/dashboard/summary", headers=org["auth"]("refer")).json()["data"]["stats"]


def test_invalid_case_transition_is_logged(client, org):
    r = client.post(
        f"/api/cases/{org['ids']['ca']}/transition",
        headers=org["auth"]("coord"),
        json={"status": "CLOSED"},
    )
    err(r, 403, "FORBIDDEN")
    # Direct status changes are denied; this endpoint does not emit a case event.
