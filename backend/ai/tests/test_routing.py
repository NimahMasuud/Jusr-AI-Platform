from app.config import Settings, load_json
from app.providers.rules import RuleProvider
from app.models import ReferralTargetRequest


def provider():
    st = Settings()
    return RuleProvider(load_json(st.config_dir, "urgency_criteria.json"), load_json(st.config_dir, "routing_table.json"))


def ask(spec):
    return provider().referral_target(ReferralTargetRequest(case_id="C", specialty_needed=spec))


def test_single_specialty():
    r = ask("Primary care")
    o = r.content["options"][0]
    assert o["primary"]["facilityCode"] == "Facility B" and o["time_to_accept_urgent"] == "1 working day"


def test_combined_specialty_text_from_the_urgency_rules_returns_each_match():
    r = ask("Haematology or General medicine")
    assert [o["specialty"] for o in r.content["options"]] == ["Haematology", "General medicine"]


def test_alias_and_case_do_not_matter():
    assert ask("OBSTETRICS").content["options"][0]["specialty"] == "Obstetrics (antenatal care)"


def test_unknown_specialty_makes_no_suggestion():
    assert ask("Dermatology").status == "no_suggestion"
