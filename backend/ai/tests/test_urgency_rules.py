"""Urgency suggestions follow Kafilat's draft mock criteria (config/urgency_criteria.json).
These tests do not judge the clinical values. They check the code applies the file as written."""
import json
from pathlib import Path
import pytest
from app.config import Settings, load_json
from app.urgency import Criteria, evaluate

FIX = Path(__file__).parent / "fixtures" / "kafilat_row_expectations.json"


@pytest.fixture(scope="module")
def criteria():
    return Criteria(load_json(Settings().config_dir, "urgency_criteria.json"))


def top(criteria, **item):
    return evaluate(criteria, [{"test": item.pop("test"), **item}])


def test_every_row_in_kafilats_sheet_gets_the_suggestion_she_expects(criteria):
    rows = json.loads(FIX.read_text())["rows"]
    assert len(rows) == 59
    for r in rows:
        item = {k: v for k, v in r.items() if k in ("test", "value", "text")}
        ev = evaluate(criteria, [item])
        got = "not_evaluated" if ev["suggestion"] is None else ev["suggestion"]
        assert got == r["expected"], f"{item} gave {got}, expected {r['expected']}"


@pytest.mark.parametrize("value,expected", [
    (22, "urgent"), (22.5, "clinician_decides"), (29.9, "clinician_decides"), (30, "routine"), (36.9, "routine"),
    (37, "no_suggestion"), (54, "no_suggestion"), (54.1, "clinician_decides")])
def test_pcv_band_edges(criteria, value, expected):
    assert top(criteria, test="PCV - HAEM", value=value)["suggestion"] == expected


def test_most_severe_result_drives_the_suggestion(criteria):
    ev = evaluate(criteria, [{"test": "PCV - HAEM", "value": 34}, {"test": "HIV - CHM", "text": "Reactive"}])
    assert ev["suggestion"] == "clinician_decides"
    assert ev["confidential"] is True                       # HIV needs extra confidentiality


def test_positive_and_non_reactive_words(criteria):
    assert top(criteria, test="HBSAG - HAEM", text="Positive")["suggestion"] == "clinician_decides"
    assert top(criteria, test="HBSAG - HAEM", text="Non-reactive")["suggestion"] == "no_suggestion"
    assert top(criteria, test="HBSAG - HAEM", text="indeterminate")["suggestion"] is None   # never guess


def test_units_are_converted_or_refused_never_guessed(criteria):
    assert top(criteria, test="Platelet count", value=40000, unit="/mm3")["suggestion"] == "urgent"   # 40 x10^9/L
    assert top(criteria, test="Platelet count", value=40, unit="x10^9/L")["suggestion"] == "urgent"
    ev = top(criteria, test="MCV", value=70, unit="um")      # the listing's garbled unit
    assert ev["suggestion"] is None and "not recognised" in ev["notEvaluated"][0]["why"]
    ev = top(criteria, test="Albumin", value=2.0, unit="mg/dL")
    assert ev["suggestion"] is None


def test_missing_unit_is_assumed_but_noted(criteria):
    ev = top(criteria, test="Haemoglobin", value=6.5)
    assert ev["suggestion"] == "urgent"
    assert any("assumed" in n for n in ev["notes"])


def test_enzymes_need_the_labs_upper_limit(criteria):
    assert top(criteria, test="ALT", value=300)["suggestion"] is None
    assert top(criteria, test="ALT", value=300, upperLimit=40)["suggestion"] == "urgent"      # 7.5 x
    assert top(criteria, test="ALT", value=100, upperLimit=40)["suggestion"] == "routine"
    assert top(criteria, test="ALT", value=30, upperLimit=40)["suggestion"] == "no_suggestion"


def test_unnamed_sub_tests_and_unknown_tests_are_not_guessed(criteria):
    assert top(criteria, test="FULL BLOOD COUNT - HAEM", value=5)["suggestion"] is None
    assert top(criteria, test="SOME NEW TEST", value=5)["suggestion"] is None


def test_value_between_bands_is_not_guessed(criteria):
    ev = top(criteria, test="Platelet count", value=600)    # above normal, below the 1000 rule
    assert ev["suggestion"] is None and "no rule covers this band" in ev["notEvaluated"][0]["why"]
