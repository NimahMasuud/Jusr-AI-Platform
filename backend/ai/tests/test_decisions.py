from conftest import CLIN, COORD, RECV

BASE = "/ai/v1"


def make_urgency(client):
    r = client.post(f"{BASE}/suggestions/urgency", headers=CLIN, json={
        "caseId": "C1", "results": [{"test": "PCV - HAEM", "value": 22}]})
    return r.json()["suggestion"]["id"]


def test_wrong_role_cannot_approve_and_refusal_is_logged(client):
    sid = make_urgency(client)
    r = client.post(f"{BASE}/suggestions/{sid}/decision", headers=COORD, json={"decision": "approve"})
    assert r.status_code == 403
    assert "cannot approve" in r.json()["error"]["message"]
    audit = client.get(f"{BASE}/audit", headers=COORD, params={"caseId": "C1"}).json()
    assert any(e["eventType"] == "decision_refused" for e in audit["entries"])
    assert client.get(f"{BASE}/suggestions/{sid}", headers=COORD).json()["status"] == "pending"


def test_receiving_clinician_cannot_approve_urgency_suggestion(client):
    """Kafilat: the referring clinician sets urgency; the receiving clinician changes it on acceptance, a separate logged step."""
    sid = make_urgency(client)
    r = client.post(f"{BASE}/suggestions/{sid}/decision", headers=RECV, json={"decision": "approve"})
    assert r.status_code == 403


def test_clinician_approves_and_it_is_logged(client):
    sid = make_urgency(client)
    r = client.post(f"{BASE}/suggestions/{sid}/decision", headers=CLIN, json={"decision": "approve", "note": "agreed"})
    s = r.json()
    assert s["status"] == "accepted"
    assert s["decidedBy"] == "STAFF-014" and s["decidedRole"] == "referring_clinician"
    audit = client.get(f"{BASE}/audit", headers=COORD).json()
    assert audit["chainValid"] is True
    assert any(e["eventType"] == "suggestion_accepted" for e in audit["entries"])


def test_edit_keeps_original_and_needs_content(client):
    sid = make_urgency(client)
    bad = client.post(f"{BASE}/suggestions/{sid}/decision", headers=CLIN, json={"decision": "edit"})
    assert bad.status_code == 422
    r = client.post(f"{BASE}/suggestions/{sid}/decision", headers=CLIN, json={
        "decision": "edit", "editedContent": {"suggestedUrgency": "routine"}})
    s = r.json()
    assert s["status"] == "edited"
    assert s["content"]["suggestedUrgency"] == "urgent"            # original untouched
    assert s["editedContent"]["suggestedUrgency"] == "routine"


def test_cannot_decide_twice(client):
    sid = make_urgency(client)
    client.post(f"{BASE}/suggestions/{sid}/decision", headers=CLIN, json={"decision": "reject"})
    r = client.post(f"{BASE}/suggestions/{sid}/decision", headers=CLIN, json={"decision": "approve"})
    assert r.status_code == 409


def test_unknown_suggestion_is_404(client):
    r = client.post(f"{BASE}/suggestions/nope/decision", headers=CLIN, json={"decision": "approve"})
    assert r.status_code == 404
