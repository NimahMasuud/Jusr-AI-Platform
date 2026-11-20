import json
from conftest import CLIN, COORD, PATIENT, SAMPLES

BASE = "/ai/v1"


def read_sample(name):
    return (SAMPLES / name).read_text()


def test_document_read_stores_suggestion_with_exact_quotes(client):
    r = client.post(f"{BASE}/suggestions/document-read", headers=COORD, json={
        "caseId": "SIM-0001", "documentId": "doc-1", "documentText": read_sample("referral_letter_01.txt")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "suggested"
    s = body["suggestion"]
    assert s["status"] == "pending"                       # R-02: waits for a person
    assert s["simulated"] is True                          # R-05
    assert s["completeness"] == "complete"
    assert s["content"]["fields"]["resultValue"] == "22"
    assert all(src["quote"] for src in s["sources"])       # R-02: every field has its source
    got = client.get(f"{BASE}/suggestions/{s['id']}", headers=COORD)
    assert got.json()["id"] == s["id"]


def test_incomplete_document_is_marked_partial(client):
    r = client.post(f"{BASE}/suggestions/document-read", headers=COORD, json={
        "caseId": "SIM-0002", "documentId": "doc-2", "documentText": read_sample("lab_report_02_incomplete.txt")})
    s = r.json()["suggestion"]
    assert s["completeness"] == "partial"
    assert any("Not found" in n for n in s["notices"])


def test_unreadable_document_gives_no_suggestion_and_manual_instruction(client):
    r = client.post(f"{BASE}/suggestions/document-read", headers=COORD, json={
        "caseId": "C", "documentId": "d", "documentText": "nothing useful here"})
    body = r.json()
    assert body["status"] == "no_suggestion"
    assert body["suggestion"] is None
    assert "by hand" in body["manualInstruction"]


def test_message_draft_says_simulated_and_flags_translation(client):
    r = client.post(f"{BASE}/suggestions/message-draft", headers=COORD, json={
        "caseId": "C", "language": "yo", "urgency": "routine",
        "nextStep": "book a follow-up test", "contact": "Example Clinic, 000-000"})
    s = r.json()["suggestion"]
    assert "simulated message" in s["content"]["text"]     # R-05
    assert s["content"]["needsTranslationReview"] is True
    assert s["status"] == "pending"


def test_urgency_suggests_but_does_not_decide(client):
    r = client.post(f"{BASE}/suggestions/urgency", headers=CLIN, json={
        "caseId": "C", "results": [{"test": "PCV - HAEM", "value": 22}]})
    s = r.json()["suggestion"]
    assert s["content"]["suggestedUrgency"] == "urgent"
    assert s["content"]["matchedRules"][0]["ruleId"] == "PCV-1"
    assert s["status"] == "pending"
    assert any("DRAFT MOCK" in n for n in s["notices"])


def test_urgency_negative_result_is_not_actionable(client):
    r = client.post(f"{BASE}/suggestions/urgency", headers=CLIN, json={
        "caseId": "C", "results": [{"test": "HBSAG - HAEM", "text": "0 Negative"}]})
    body = r.json()
    assert body["suggestion"]["content"]["suggestedUrgency"] == "no_suggestion"
    assert "Not actionable" in body["message"]


def test_urgency_with_missing_values_makes_no_suggestion(client):
    r = client.post(f"{BASE}/suggestions/urgency", headers=CLIN, json={
        "caseId": "C", "results": [{"test": "FULL BLOOD COUNT - HAEM"}]})
    body = r.json()
    assert body["status"] == "no_suggestion"
    assert body["suggestion"] is None
    assert "sub-test is not named" in body["message"]


def test_summary_cites_real_events(client):
    events = json.loads(read_sample("events_case_SIM-0001.json"))
    r = client.post(f"{BASE}/suggestions/summary", headers=CLIN, json={"caseId": "SIM-0001", "events": events})
    bullets = r.json()["suggestion"]["content"]["bullets"]
    assert len(bullets) == 3
    valid = {e["eventId"] for e in events}
    assert all(set(b["sources"]) <= valid for b in bullets)


def test_referral_target_from_routing_table(client):
    r = client.post(f"{BASE}/suggestions/referral-target", headers=CLIN, json={
        "caseId": "C", "specialtyNeeded": "Haematology"})
    opts = r.json()["suggestion"]["content"]["options"]
    assert opts[0]["primary"]["facilityCode"] == "Facility C"
    assert opts[0]["backup"]["facilityCode"] == "Facility D"
    assert opts[0]["timeToAcceptUrgent"] == "2 hours"


def test_patient_cannot_ask_for_ai_suggestions(client):
    r = client.post(f"{BASE}/suggestions/summary", headers=PATIENT, json={"caseId": "C", "events": []})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ROLE_CANNOT_REQUEST"


def test_missing_login_gives_plain_error_shape(client):
    r = client.post(f"{BASE}/suggestions/summary", json={"caseId": "C", "events": []})
    assert r.status_code == 401
    body = r.json()
    assert body["success"] is False
    assert set(body["error"]) == {"code", "message", "details"}


def test_bad_request_gives_plain_error_shape(client):
    r = client.post(f"{BASE}/suggestions/message-draft", headers=COORD, json={"caseId": "C"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_response_keys_are_camel_case(client):
    r = client.post(f"{BASE}/suggestions/summary", headers=CLIN, json={
        "caseId": "C", "events": [{"eventId": "E1", "timestamp": "2026-11-02T09:00:00Z",
                                   "type": "result_received", "text": "x"}]})
    s = r.json()["suggestion"]
    assert {"caseId", "requestedBy", "createdAt", "editedContent"} <= set(s)
    assert "case_id" not in s
    assert "manualInstruction" in r.json()


def test_list_filters_by_camel_case_param(client):
    for cid in ("A", "B"):
        client.post(f"{BASE}/suggestions/summary", headers=CLIN, json={"caseId": cid, "events": [
            {"eventId": "E1", "timestamp": "2026-11-02T09:00:00Z", "type": "x", "text": "t"}]})
    r = client.get(f"{BASE}/suggestions", headers=CLIN, params={"caseId": "A"})
    assert [s["caseId"] for s in r.json()] == ["A"]
