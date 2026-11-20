"""Backend mode: results are submitted to the backend as PENDING suggestions, in the backend's own payload shapes."""
import json
import shutil
import pytest
from fastapi.testclient import TestClient
from app.backend_client import BackendClient
from app.config import Settings
from app.main import create_app
from conftest import COORD, CLIN, ROOT, SAMPLES
from fake_backend import EMAIL, PASSWORD, FakeBackend

BASE = "/ai/v1/submit"
FACILITIES = {"Facility A": "fac-a", "Facility B": "fac-b", "Facility C": "fac-c", "Facility D": "fac-d"}


@pytest.fixture(scope="module")
def backend():
    b = FakeBackend(); b.start()
    yield b
    b.stop()


@pytest.fixture
def cfg(tmp_path):
    d = tmp_path / "config"
    shutil.copytree(ROOT / "config", d)
    (d / "facility_ids.json").write_text(json.dumps({"ids": FACILITIES}))
    return d


def make_client(backend, cfg, **kw):
    backend.state.update({"received": [], "reject": False, "expire_next": False})
    st = Settings(config_dir=cfg, backend_url=kw.pop("url", backend.url), ai_service_email=EMAIL, ai_service_password=PASSWORD)
    return TestClient(create_app(st))


def letter():
    return (SAMPLES / "referral_letter_01.txt").read_text()


def test_urgency_is_submitted_as_a_pending_urgent_suggestion(backend, cfg):
    c = make_client(backend, cfg)
    r = c.post(f"{BASE}/urgency", headers=CLIN, json={"caseId": "CASE-1", "results": [{"test": "PCV - HAEM", "value": 22}]})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "submitted"
    assert body["backendSuggestion"]["status"] == "PENDING"
    sent = backend.state["received"][0]
    assert sent["kind"] == "URGENCY" and sent["caseId"] == "CASE-1"
    assert sent["payload"]["priority"] == "URGENT" and sent["payload"]["actionability"] == "ACTIONABLE"
    assert sent["model"] == "rules"


@pytest.mark.parametrize("item,priority,action", [
    ({"test": "PCV - HAEM", "value": 26}, "HIGH", "NEEDS_REVIEW"),
    ({"test": "PCV - HAEM", "value": 34}, "NORMAL", "ACTIONABLE"),
    ({"test": "HBSAG - HAEM", "text": "0 Negative"}, "NORMAL", "NOT_ACTIONABLE")])
def test_urgency_mapping(backend, cfg, item, priority, action):
    c = make_client(backend, cfg)
    c.post(f"{BASE}/urgency", headers=CLIN, json={"caseId": "C", "results": [item]})
    p = backend.state["received"][0]["payload"]
    assert (p["priority"], p["actionability"]) == (priority, action)


def test_nothing_is_sent_when_there_is_no_suggestion(backend, cfg):
    c = make_client(backend, cfg)
    r = c.post(f"{BASE}/urgency", headers=CLIN, json={"caseId": "C", "results": [{"test": "FULL BLOOD COUNT - HAEM"}]})
    assert r.json()["status"] == "no_suggestion"
    assert backend.state["received"] == []


def test_summary_cites_audit_events(backend, cfg):
    c = make_client(backend, cfg)
    events = json.loads((SAMPLES / "events_case_SIM-0001.json").read_text())
    r = c.post(f"{BASE}/summary", headers=CLIN, json={"caseId": "C", "events": events})
    assert r.json()["status"] == "submitted"
    p = backend.state["received"][0]["payload"]
    assert {c_["sourceId"] for c_ in p["citations"]} == {"E1", "E2", "E3"}
    assert all(c_["sourceType"] == "AUDIT_EVENT" for c_ in p["citations"])


def test_message_draft_goes_with_its_channel(backend, cfg):
    c = make_client(backend, cfg)
    c.post(f"{BASE}/message-draft", headers=COORD, json={"caseId": "C", "channel": "EMAIL", "urgency": "routine",
                                                          "nextStep": "book a test", "contact": "Clinic 000"})
    p = backend.state["received"][0]["payload"]
    assert p["channel"] == "EMAIL" and "simulated message" in p["body"]


def test_unreviewed_translation_is_not_submitted(backend, cfg):
    c = make_client(backend, cfg)
    r = c.post(f"{BASE}/message-draft", headers=COORD, json={"caseId": "C", "language": "yo", "urgency": "routine",
                                                              "nextStep": "book a test", "contact": "Clinic 000"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CANNOT_SUBMIT"
    assert backend.state["received"] == []


def test_referral_target_uses_the_facility_ids(backend, cfg):
    c = make_client(backend, cfg)
    r = c.post(f"{BASE}/referral-target", headers=CLIN, json={"caseId": "C", "specialtyNeeded": "Haematology"})
    assert r.status_code == 200
    p = backend.state["received"][0]["payload"]
    assert p["receivingFacilityId"] == "fac-c"
    assert [a["receivingFacilityId"] for a in p["alternatives"]] == ["fac-d"]


def test_referral_resolves_facility_codes_through_the_backend(backend, cfg):
    (cfg / "facility_ids.json").write_text(json.dumps({
        "ids": {},
        "codeAliases": {"Facility A": "JUSR-DEMO", "Facility B": "DEMO-RRH",
                        "Facility C": "DEMO-DC", "Facility D": "DEMO-RRH"},
    }))
    c = make_client(backend, cfg)
    r = c.post(f"{BASE}/referral-target", headers=CLIN, json={"caseId": "C", "specialtyNeeded": "Colposcopy"})
    assert r.status_code == 200, r.text
    p = backend.state["received"][0]["payload"]
    assert p["receivingFacilityId"] == "fac-b"
    assert [a["receivingFacilityId"] for a in p["alternatives"]] == ["fac-a"]


def test_referral_without_facility_ids_is_refused_in_plain_words(backend, tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")    # facility_ids.json is empty here
    (tmp_path / "config" / "facility_ids.json").write_text('{"ids": {}}')
    c = make_client(backend, tmp_path / "config")
    r = c.post(f"{BASE}/referral-target", headers=CLIN, json={"caseId": "C", "specialtyNeeded": "Haematology"})
    assert r.status_code == 422
    assert "no backend ID" in r.json()["error"]["message"]
    assert backend.state["received"] == []


def test_intake_needs_patient_and_facility_ids_and_omits_case_id(backend, cfg):
    c = make_client(backend, cfg)
    body = {"caseId": "CASE-SIM-1", "documentId": "d1", "documentText": letter()}
    assert c.post(f"{BASE}/intake", headers=COORD, json=body).status_code == 422
    r = c.post(f"{BASE}/intake", headers=COORD, json={**body, "patientId": "pat-1", "facilityId": "fac-a"})
    assert r.status_code == 200
    sent = backend.state["received"][0]
    assert sent["kind"] == "INTAKE" and "caseId" not in sent
    assert sent["payload"]["priority"] == "URGENT"          # PCV 22 from the letter
    assert sent["payload"]["caseId"] == "CASE-SIM-1"


def test_backend_not_configured(cfg):
    c = TestClient(create_app(Settings(config_dir=cfg)))
    r = c.post(f"{BASE}/urgency", headers=CLIN, json={"caseId": "C", "results": [{"test": "PCV - HAEM", "value": 22}]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "BACKEND_NOT_CONFIGURED"


def test_backend_down_gives_a_plain_error(backend, cfg):
    c = make_client(backend, cfg, url="http://127.0.0.1:9")
    r = c.post(f"{BASE}/urgency", headers=CLIN, json={"caseId": "C", "results": [{"test": "PCV - HAEM", "value": 22}]})
    assert r.status_code == 502 and r.json()["error"]["code"] == "BACKEND_UNAVAILABLE"


def test_backend_refusal_is_passed_on(backend, cfg):
    c = make_client(backend, cfg)
    backend.state["reject"] = True
    r = c.post(f"{BASE}/urgency", headers=CLIN, json={"caseId": "C", "results": [{"test": "PCV - HAEM", "value": 22}]})
    assert r.status_code == 502 and r.json()["error"]["code"] == "BACKEND_REJECTED"
    assert "Payload does not match" in r.json()["error"]["message"]


def test_expired_token_signs_in_again_once(backend, cfg):
    c = make_client(backend, cfg)
    ok = {"caseId": "C", "results": [{"test": "PCV - HAEM", "value": 22}]}
    c.post(f"{BASE}/urgency", headers=CLIN, json=ok)
    before = backend.state["logins"]
    backend.state["expire_next"] = True
    assert c.post(f"{BASE}/urgency", headers=CLIN, json=ok).status_code == 200
    assert backend.state["logins"] == before + 1


def test_R08_the_backend_client_can_only_sign_in_submit_and_read_facilities():
    public = {n for n in dir(BackendClient) if not n.startswith("_")}
    assert public == {"login", "submit_suggestion", "list_facilities"}  # no way to change a status, owner, urgency or closure
