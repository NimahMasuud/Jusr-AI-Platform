"""The model call is not tested (needs a key). The checks applied to its output are."""
import json
import pytest
from app.models import CaseEvent, DocumentReadRequest, SummaryRequest
from app.providers.base import ProviderError
from app.providers.llm import AnthropicProvider
from app.providers.rules import RuleProvider


def fake_provider(reply: str) -> AnthropicProvider:
    p = object.__new__(AnthropicProvider)
    p._rules, p._simulated, p._model = RuleProvider({}, {}), True, "x"
    p._ask = lambda system, user: reply
    return p


DOC = "Patient ref: SIM-1\nFacility: Example Facility One\nTest: EXAMPLE_TEST_A\nResult: 120\nDate: 2026-11-02"


def test_invented_fields_are_dropped():
    reply = json.dumps({"fields": [
        {"name": "result_value", "value": "120", "quote": "Result: 120"},
        {"name": "ordering_clinician", "value": "Dr Invented", "quote": "Ordering clinician: Dr Invented"},
    ]})
    res = fake_provider(reply).document_read(DocumentReadRequest(case_id="C", document_id="d", document_text=DOC))
    assert res.content["fields"] == {"result_value": "120"}
    assert any("dropped" in n for n in res.notices)


def test_all_invented_means_no_suggestion():
    reply = json.dumps({"fields": [{"name": "result_value", "value": "999", "quote": "Result: 999"}]})
    res = fake_provider(reply).document_read(DocumentReadRequest(case_id="C", document_id="d", document_text=DOC))
    assert res.status == "no_suggestion"


def test_summary_lines_must_cite_real_events():
    events = [CaseEvent(event_id="E1", timestamp="2026-11-02T09:00:00Z", type="result_received", text="x")]
    reply = json.dumps({"bullets": [{"text": "ok", "sources": ["E1"]}, {"text": "made up", "sources": ["E9"]}]})
    res = fake_provider(reply).summary(SummaryRequest(case_id="C", events=events))
    assert len(res.content["bullets"]) == 1
    assert any("dropped" in n for n in res.notices)


def test_unreadable_model_output_raises_so_the_fallback_runs():
    with pytest.raises(ProviderError):
        fake_provider("this is not json").document_read(
            DocumentReadRequest(case_id="C", document_id="d", document_text=DOC))
