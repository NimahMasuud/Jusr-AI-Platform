"""The OpenAI-compatible provider (Ollama with Qwen 2.5, LM Studio, vLLM), tested against a stub server.
A real model is not involved: these tests check the plumbing and the checks on what comes back."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.models import DocumentReadRequest
from app.providers.base import ProviderError
from app.providers.llm import OpenAICompatibleProvider
from app.providers.rules import RuleProvider
from conftest import COORD, SAMPLES

LETTER = (SAMPLES / "referral_letter_01.txt").read_text()


class Stub:
    def __init__(self, reply):
        stub = self
        self.reply, self.requests = reply, []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                stub.requests.append(json.loads(self.rfile.read(n)))
                out = json.dumps({"choices": [{"message": {"role": "assistant", "content": stub.reply}}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a): pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def rules():
    return RuleProvider({}, {})


def provider(url, rules):
    return OpenAICompatibleProvider(url, "qwen2.5:7b", None, 5, rules)


def test_reads_a_document_and_drops_invented_fields(rules):
    stub = Stub(json.dumps({"fields": [
        {"name": "test_name", "value": "PCV - HAEM", "quote": "Test: PCV - HAEM"},
        {"name": "result_value", "value": "22", "quote": "Result: 22"},
        {"name": "ordering_clinician", "value": "Dr Invented", "quote": "Ordering clinician: Dr Invented"}]}))
    try:
        res = provider(stub.url, rules).document_read(DocumentReadRequest(case_id="C", document_id="d", document_text=LETTER))
    finally:
        stub.close()
    assert res.content["fields"] == {"test_name": "PCV - HAEM", "result_value": "22"}
    assert any("dropped" in n for n in res.notices)
    sent = stub.requests[0]
    assert sent["model"] == "qwen2.5:7b" and sent["temperature"] == 0
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]


def test_json_in_a_code_fence_is_accepted(rules):
    stub = Stub("```json\n" + json.dumps({"fields": [{"name": "result_value", "value": "22", "quote": "Result: 22"}]}) + "\n```")
    try:
        res = provider(stub.url, rules).document_read(DocumentReadRequest(case_id="C", document_id="d", document_text=LETTER))
    finally:
        stub.close()
    assert res.content["fields"] == {"result_value": "22"}


def test_a_model_that_is_not_running_raises_so_the_fallback_can_run(rules):
    with pytest.raises(ProviderError):
        provider("http://127.0.0.1:9/v1", rules).document_read(
            DocumentReadRequest(case_id="C", document_id="d", document_text=LETTER))


def test_app_uses_the_model_and_falls_back_to_rules_when_it_is_down():
    c = TestClient(create_app(Settings(provider="openai_compatible", llm_base_url="http://127.0.0.1:9/v1")))
    assert c.get("/health").json()["provider"] == "openai_compatible"
    r = c.post("/ai/v1/suggestions/document-read", headers=COORD, json={
        "caseId": "C", "documentId": "d", "documentText": LETTER})
    body = r.json()
    assert body["status"] == "suggested"
    assert body["suggestion"]["provider"] == "rules (fallback)"             # R-04
    assert body["suggestion"]["content"]["fields"]["testName"] == "PCV - HAEM"
