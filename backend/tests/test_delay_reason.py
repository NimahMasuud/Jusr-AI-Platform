import pytest
from datetime import datetime, timedelta, timezone


def err(r, status, code=None):
    assert r.status_code == status, r.text
    assert r.json()["success"] is False
    if code:
        assert r.json()["error"]["code"] == code


def delay(client, org, who="coord", **body):
    return client.post(
        f"/api/cases/{org['ids']['ca']}/delay-reason",
        headers=org["auth"](who),
        json=body or {"code": "RESULT_OR_DATA_MISSING"},
    )


def transition(client, org, status, who="coord", **extra):
    return client.post(
        f"/api/cases/{org['ids']['ca']}/transition",
        headers=org["auth"](who),
        json={"status": status, **extra},
    )


def events(client, org):
    return client.get(
        f"/api/cases/{org['ids']['ca']}/events",
        headers=org["auth"]("national"),
    ).json()["data"]


def acknowledge(client, org):
    return client.post(
        f"/api/cases/{org['ids']['ca']}/assisted-responses",
        headers=org["auth"]("coord"),
        json={
            "acknowledged": True,
            "understood": "YES",
            "confidence": 4,
            "explanationStatus": "EXPLAINED",
            "callbackRequested": False,
        },
    )


def test_direct_transition_is_blocked(client, org):
    err(transition(client, org, "IN_PROGRESS"), 403, "FORBIDDEN")


def test_invalid_direct_transition_is_also_blocked(client, org):
    err(transition(client, org, "CLOSED"), 403, "FORBIDDEN")


def test_delay_reason_validation_and_permissions(client, org):
    err(delay(client, org, code="BOGUS"), 422, "VALIDATION_ERROR")
    err(delay(client, org, code="OTHER"), 422, "VALIDATION_ERROR")
    err(delay(client, org, code="OTHER", note="   "), 422, "VALIDATION_ERROR")

    r = delay(client, org, code="OTHER", note="Clinic flooded")
    assert r.status_code == 200, r.text
    assert "OVERDUE" not in r.json()["data"]["flags"]
    assert "URGENT" in r.json()["data"]["flags"]

    for who, status in (("fadmin", 403), ("recv", 404), ("ai", 403), ("coordB", 404)):
        err(delay(client, org, who), status)


def test_delay_reason_only_on_overdue_cases(client, org):
    r = client.post(
        f"/api/cases/{org['ids']['cb']}/delay-reason",
        headers=org["auth"]("coordB"),
        json={"code": "NO_SLOT_AVAILABLE"},
    )
    err(r, 409, "CASE_NOT_OVERDUE")


def test_reason_can_be_updated_and_is_audited_with_role(client, org):
    first = delay(client, org, code="RESULT_OR_DATA_MISSING")
    assert first.status_code == 200, first.text
    second = delay(client, org, who="refer", code="PATIENT_UNREACHABLE", note="Phone off")

    assert second.status_code == 200, second.text
    assert second.json()["data"]["delayReason"]["code"] == "PATIENT_UNREACHABLE"

    ev = [e for e in events(client, org) if e["eventType"] == "DELAY_REASON_RECORDED"]
    assert [e["actorRole"] for e in ev] == ["COORDINATOR", "REFERRING_CLINICIAN"]


def test_worklist_and_dashboard_expose_it(client, org):
    # The overdue synchronizer suppresses OVERDUE only when the reason was
    # recorded after the case entered its current status. Normalize the fixture
    # timestamps so this test exercises that intended rule.
    from app.models.entities import Case

    db = client.session_factory()
    case = db.get(Case, org["ids"]["ca"])
    earlier = datetime.now(timezone.utc) - timedelta(days=1)
    case.status_entered_at = earlier
    case.due_at = earlier
    db.commit()
    db.close()
    def row():
        cases = client.get(
            "/api/worklist", headers=org["auth"]("coord")
        ).json()["data"]["cases"]
        return next(c for c in cases if c["caseId"] == "CA")

    assert row()["delayReasonRequired"] is True
    assert row()["delayReason"] is None

    assert client.get(
        "/api/dashboard/summary", headers=org["auth"]("coord")
    ).json()["data"]["stats"]["missingDelayReason"] == 1

    r = delay(client, org)
    assert r.status_code == 200, r.text

    assert row()["delayReasonRequired"] is False
    assert row()["delayReason"]["code"] == "RESULT_OR_DATA_MISSING"

    assert client.get(
        "/api/dashboard/summary", headers=org["auth"]("coord")
    ).json()["data"]["stats"]["missingDelayReason"] == 0


def test_referral_requires_acknowledgement_not_delay_reason(client, org):
    body = {
        "caseId": org["ids"]["ca"],
        "receivingFacilityId": org["ids"]["fb"],
        "reason": "Needs colposcopy",
    }
    # The referral workflow's T9 guard requires patient acknowledgement and understanding.
    r = client.post("/api/referrals", headers=org["auth"]("refer"), json=body)
    err(r, 422, "ACKNOWLEDGEMENT_REQUIRED")

    ack = acknowledge(client, org)
    assert ack.status_code == 200, ack.text
    r = client.post("/api/referrals", headers=org["auth"]("refer"), json=body)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "SENT"


def test_code_list(client, org):
    codes = client.get(
        "/api/cases/delay-reasons",
        headers=org["auth"]("coord"),
    ).json()["data"]

    assert "OTHER" in codes
    assert "RESULT_OR_DATA_MISSING" in codes
    assert "AWAITING_RESULTS" not in codes
