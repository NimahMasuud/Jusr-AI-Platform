"""R-04: the flow must still work by hand if an AI helper fails."""
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderError
from conftest import COORD, SAMPLES

BASE = "/ai/v1"


class BrokenProvider:
    name = "broken"

    def __getattr__(self, item):
        def boom(*a, **k):
            raise ProviderError("down")
        return boom


def test_failed_provider_falls_back_to_rules_and_says_so():
    c = TestClient(create_app(Settings(), provider=BrokenProvider()))
    r = c.post(f"{BASE}/suggestions/document-read", headers=COORD, json={
        "caseId": "C", "documentId": "d", "documentText": (SAMPLES / "referral_letter_01.txt").read_text()})
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "suggested"
    assert body["suggestion"]["provider"] == "rules (fallback)"
    assert any("not available" in n for n in body["suggestion"]["notices"])
    audit = c.get(f"{BASE}/audit", headers=COORD).json()["entries"]
    assert any(e["eventType"] == "ai_helper_failed" for e in audit)


def test_failed_provider_and_nothing_to_fall_back_on_gives_manual_instruction():
    c = TestClient(create_app(Settings(), provider=BrokenProvider()))
    r = c.post(f"{BASE}/suggestions/document-read", headers=COORD, json={
        "caseId": "C", "documentId": "d", "documentText": "no labelled lines here"})
    body = r.json()
    assert r.status_code == 200                     # never an error that blocks the flow
    assert body["status"] == "unavailable"
    assert "by hand" in body["manualInstruction"]
